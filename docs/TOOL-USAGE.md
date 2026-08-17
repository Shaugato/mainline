<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# TOOL USAGE — which CockroachDB and AWS services, and how

This is the hackathon's *"documentation of which CockroachDB and AWS services were used
and how"*. The bar is **at least two CockroachDB tools and at least one AWS service**.
MAINLINE documents
4 [src: evidence/tool-usage/crdb-features.json#totals.by_kind.tool] CockroachDB tools —
inside which 10 [src: evidence/tool-usage/crdb-features.json#totals.by_kind.feature]
engine features are separately accounted, because counting a feature as a tool to clear a
bar is the kind of arithmetic this repository exists to refuse — and
12 [src: evidence/tool-usage/aws-services.json#totals.by_kind.service] AWS services.

It is written to be **checked line by line, not read**. Every count below carries a
`[src: …]` reference in the style of [`docs/HONESTY.md`](HONESTY.md), every mechanism
carries a file and a line number, and every entry carries a verdict saying whether the
thing has actually run.

```bash
python scripts/submission/capture_tool_evidence.py --check   # non-zero if anything here is stale
```

That command is standard-library only, takes no network and no credential, and re-derives
both evidence files from the tree. A document about which cloud services a project uses
must not require those cloud services in order to check it.

> **It exited `2` on 2026-08-14 and it exits `0` on 2026-08-15. Both readings stay on this
> page, because the red is the part that proves the green is worth anything.**
>
> *The red.* Not a count — two **anchors**. The generator declared the Lambda row's anchor as
> `infra/modules/demo-api/main.tf:333` for `authorization_type` and the SSM row's as `:215`
> for `ssm:GetParameter` (`scripts/submission/capture_tool_evidence.py`, the `anchor=` /
> `anchor_must_contain=` pair on each row); that module has grown past 978 lines, `:333` had
> slid onto `handler = "mainline_demo_api.app.handler"` and `:215` onto a bare `#`. Both
> resolved perfectly and neither said anything. The generator **refuses to write anything**
> while an anchor has drifted, and `--print` refuses identically, so `scan.files_scanned`
> could not be re-derived on that machine that day and was recorded as `UNRESOLVED` rather
> than guessed. `scripts/aws/verify_evidence.py` reported the same pair under `[CEN-ANCHORS]`
> earlier on 2026-08-14; re-run later the same day it **passed** — `1016` assertions across
> `40` of `40` invariants — because it reads the JSON, and the JSON had been hand-edited to
> `:432` and `:280` while the generator had not. Two programs that agreed then disagreed, and
> the one still refusing was the one reading the authoritative side.
>
> *The fix, and where it had to land.* **The generator's table is the authoritative side and
> the JSON is derived from it**; moving the derived file alone did not close the finding, it
> only made two files disagree about which line a reader should open. So on 2026-08-15 the
> `anchor=` pair in `capture_tool_evidence.py` moved to `:432` and `:280` — located by
> searching for the quoted text, not by counting an offset — and both censuses were
> regenerated from it. **Nothing under `infra/` was edited to make a citation true.**
> `--check` now exits `0`, `scan.files_scanned` is
> 7884 [src: evidence/tool-usage/crdb-features.json#scan.files_scanned] again rather than
> `UNRESOLVED`, and no verdict or count on this page ever rested on any of those four line
> numbers.
>
> That refusal is the mechanism described at the end of this section working as designed, on
> the next drift after the five it was built for. **A count on this page is fresh as of the
> tree it was taken from and no longer**: several people edit this repository at once, a file
> that merely *mentions* a feature moves a `file_count`, and the command above is the only
> thing entitled to say whether these numbers are current. Run it; do not trust this
> paragraph.

**One convention, borrowed from `docs/HONESTY.md`.** A bare number carries a `[src: …]`
reference to a committed artefact. Digits inside `code spans` are **names**, not
measurements — `v26.2.5`, SQLSTATE `23514`, a byte cap of `10240` read from a named line
of source. And the blocks headed *"Measured on the pinned local node"* are transcripts of
a scratch run against the local single-node cluster; they are **reproducible, not
committed** — no artefact under `evidence/` records them, and no number in any table here
depends on one. Part 5 gives the commands.

---

## The verdict column, and why the third value exists

| verdict | means |
|---|---|
| **EXERCISED** | it ran, and a committed artefact in this repository records the result |
| **DESIGNED** | the code or configuration is complete and on disk; nothing recorded has run it end to end |
| **NOT-AVAILABLE** | checked on this platform and absent; no dependency was taken on it |

Counted across both censuses: EXERCISED
12 [src: evidence/tool-usage/crdb-features.json#totals.by_verdict.EXERCISED]
+ 6 [src: evidence/tool-usage/aws-services.json#totals.by_verdict.EXERCISED],
DESIGNED 2 [src: evidence/tool-usage/crdb-features.json#totals.by_verdict.DESIGNED]
+ 5 [src: evidence/tool-usage/aws-services.json#totals.by_verdict.DESIGNED],
NOT-AVAILABLE 1 [src: evidence/tool-usage/aws-services.json#totals.by_verdict.NOT-AVAILABLE].

**Read that asymmetry rather than skipping it.** The CockroachDB half has run. On the AWS
side the EXERCISED column was **empty** until 2026-08-11, held **three** rows until
2026-08-14 — **Bedrock inference, Bedrock embeddings and CloudWatch**, every one of them an
API call against a service AWS already operates and none of them a deployment — and holds
**six** now, because on 2026-08-14 a `terraform apply` ran. What did *not* move is as
informative as what did: **five rows are still DESIGNED** — S3 + Object Lock, KMS,
CloudTrail, CloudFront and EventBridge — which here means *the configuration is complete and
on disk and nothing recorded has run it end to end*. There is still no MAINLINE evidence
bucket, no KMS signing key, no trail, no distribution and no schedule rule. A submission
document that flattened "we called a model" and "we deployed an evidence store" into "used"
would be lying about the more important one. See [`docs/HONESTY.md`](HONESTY.md).

**A verdict moves only when a measurement moves it. Four have moved, and each names the
committed file that moved it.** `crdb_managed_mcp` was promoted DESIGNED → EXERCISED on
2026-08-12 because
[`evidence/deploy/judge-run.json`](../evidence/deploy/judge-run.json) captures a live
session against the managed endpoint; the promotion is recorded in that row's
`verdict_basis`, with the run's own `DIVERGED — KNOWN GAP` verdict intact. On 2026-08-15
**`aws_lambda`, `aws_iam` and `aws_ssm_parameter_store`** were promoted, on
[`evidence/deploy/APPLIED.md`](../evidence/deploy/APPLIED.md) — *"terraform apply 24
created, 0 changed, 0 destroyed"* — plus
[`evidence/deploy/live-health.json`](../evidence/deploy/live-health.json) (`ok true`,
`deploy_chain 271/271`) and
[`evidence/deploy/live-gate-run.json`](../evidence/deploy/live-gate-run.json) (the four
beats, verdict `PROVEN`, over HTTP). **No AWS API call earned any of those three**: this
census opens no socket, and every file behind a promotion was committed before it ran. Two
things did not move and are the reason this paragraph is worth reading. **CloudFront cannot
be promoted at all** — the account is refused new distributions, which is not a schedule
problem — and the `aws_iam` promotion is **narrower than its own row title**: what ran is
the execution role's single allow, while the deny-first evidence-store policies remain
unapplied and offline-asserted. A promotion that quietly widened its scope would be the same
offence as one made on an intention.

Everything the two Bedrock rows and the CloudWatch row rest on is under
[`evidence/aws/`](../evidence/aws/README.md), and it is checkable without our credentials:

```bash
python scripts/aws/verify_evidence.py    # stdlib only · no credential · no network
```

Every invariant it enforces is printed by `--list`: envelopes, cross-references between
artefacts, secret shapes anywhere under `evidence/`, the citations on this page, and — the
one that matters — *every EXERCISED verdict's cited artefact must exist*. It runs in CI as
[`.github/workflows/aws-evidence.yml`](../.github/workflows/aws-evidence.yml) on a fresh
checkout with no secrets configured, alongside a red half that plants one defect per family
and requires the matching invariant to fire.

**Scan set for every count below**: a filesystem walk of
7884 [src: evidence/tool-usage/crdb-features.json#scan.files_scanned] text files, caches
and build output pruned, of which
271 [src: evidence/tool-usage/crdb-features.json#scan.files_by_category.migration] are
migrations and 29 [src: evidence/tool-usage/crdb-features.json#scan.files_by_category.terraform]
are Terraform/Rego. `file_count` counts where a feature is used **and** where it is
discussed, which is why every row also names one hand-checked file and line.

**The citation check got stricter on 2026-08-12, because the weak version was passing.**
The census used to refuse only when an anchor stopped *resolving* — when the file was too
short for the line number. That proves almost nothing: a citation onto line 257 of a
500-line Terraform module resolves whatever line 257 has become. Audited by hand, **five of
the twelve AWS anchors had drifted onto a bare `}`, a `})`, a blank line,
`timeout = var.timeout`, and a fragment of an unrelated docstring** — every one of them
resolving perfectly, and every one of them sending a reader to a closing brace. Each row
now declares `anchor_must_contain`, a substring its cited line has to hold, and the
generator **refuses to write** when the line no longer holds it. The five were re-pointed;
`evidence/tool-usage/*.json` carries `anchor_resolved.line_text` and
`anchor_resolved.subject_holds` for each, so the next drift is a red gate rather than an
archaeology exercise.

---

# Part 1 · CockroachDB — four tools

**The floor is two; this section documents four — and it introduces them in the order the
judging criterion names them, not the order we happened to build them.** The Technological
Implementation criterion enumerates exactly three: *"the integration with CockroachDB tools
(**distributed vector index, MCP Server, ccloud CLI**)"*. **Agent Skills is not in that
list.** It is named separately in the submission requirements, so it earns the ≥ two-tool
floor and is documented fourth, *beyond* it — and it is also the only one of the four whose
verdict is not EXERCISED, so last is where it belongs on both counts. The numbered `Tool N`
headings below are kept at their existing numbers because other documents cite them; this
table, not the heading order, is the criterion's order.

**And it answers the question the requirement actually asks**, which is sharper than a
feature list: *"Identify which CockroachDB tools you used … and how — **what did the agent
actually do with them?**"* So every row below says what an **agent did**, not what the
repository contains.

| # | tool, in the criterion's own order | verdict | **what the agent actually did with it** |
|---|---|---|---|
| 1 | **Distributed vector index** — C-SPANN `VECTOR INDEX` | **EXERCISED** | The agent's **recall path issues prefix-constrained ANN queries** over the clause-embedding sidecars — the index named in the statement (`FROM ce@ce_ann`) with every prefix column pinned to a single value — to fetch the precursor clauses it then reasons over. **It does not trust its own recall:** the plan is read back and asserted, because a plan that degrades to a declared `FULL SCAN` returns plausible rows, so a silent degradation would be indistinguishable from working retrieval. Pinning the prefix is what makes the index traverse; **the hint is belt-and-braces, and the claim that it was load-bearing is struck** — `docs/upstream/STRIKE-LEDGER.md` §2 (F03). `skills/designing-vector-recall-prefixes/scripts/assert_prefix_index_used.py` is the committed assertion that goes red when the plan stops choosing the index. See *Tool 1 → C-SPANN vector index*. |
| 2 | **MCP Server** — CockroachDB Cloud Managed MCP | **EXERCISED** | An MCP client dialled **CockroachDB's own managed endpoint** and drove the sixteen-question judge pack over `select_query` and `explain_query` against the live Basic cluster — reading MAINLINE's contracted `mainline_audit` views **with none of our code in the read path**. It asked the general-counsel question *what is the gate refusing right now?* and `v_open_gate_summary` answered with one row, `open_blocking = 1`. **Read verbs only: no write verb was ever sent**, and the capture program enforces that at the transport rather than promising it. See *Tool 3*. |
| 3 | **`ccloud` CLI** | **EXERCISED** | Ran `ccloud auth whoami` then `ccloud cluster list -o json` and **parsed the structured output rather than screen-scraping it**, reading the cluster's version, region, plan and `spend_limit` off JSON. Then it did the harder thing: on measuring that `0.6.12` **cannot authenticate headlessly**, it did not claim the capability — headless paths use the Cloud REST API with the same key, and the limitation is published. See *Tool 2*. |
| 4 | **Agent Skills** — beyond the floor, not in the criterion | **DESIGNED** | **Nothing this repository records — stated plainly rather than dressed up.** Two authored skills and one staged upstream contribution are written for an agent to consume, and each ships an *executable assertion* instead of advice. But **no run of either script is captured under `evidence/`**, so the honest answer to *what did the agent do with them* is: they are shipped and not yet evidenced. This row is **not** promoted to EXERCISED to make the table look even. See *Tool 4*. |

Every claim in that table is unpacked, with its file, line and committed artefact, in the
section it points to. The feedback the rules invite on these same tools is at the end of
this Part.

## Tool 1 · CockroachDB itself (v26.2.5)

**The product's central claim is a database refusal, so the database is not a datastore
under this system — it is the system.** MAINLINE gates the merge of a permit-to-work: a
permit may not reach `merged` while a recalled precursor carries an obligation nobody has
signed off. That rule is enforced by constraints and triggers, so it holds against psql, a
migration script and a back-office correction alike — not only against the application
that was written to respect it.

**Where it runs.** A local single-node `cockroachdb/cockroach:v26.2.5` pinned at
`compose.yaml:31`, and CockroachDB Cloud Basic cluster `mainline-dev` in
`aws-ap-southeast-1` (Singapore). The pinned version string appears in
448 [src: evidence/tool-usage/crdb-features.json#rows.crdb_database.file_count] files.

**And, since 2026-08-13, in CI.** `.github/workflows/cluster-tests.yml` starts the same
pinned image on the runner and runs the demo API's suite against it at `--crdb=reuse`. Before
that lane existed, every workflow in this repository passed `--crdb=none`, so **every
cluster-backed test skipped and the claims on this page had never been executed by a lane.**
GitHub Actions run
[`31735341117`](https://github.com/Shaugato/mainline/actions/runs/31735341117) at
`headSha eefae1c` measured `528` collected, `518` executed, `10` skipped, `1` failed,
`0` errored — *"1 failed, 517 passed, 10 skipped in 154.21s"*.

**Its conclusion is `failure`, and the residual is stated here rather than left for a reader
to find.** The `10` skips stand against a ceiling of `1`
(`qa/cluster-known-red.json#floor.max_skipped`, beside `min_executed: 440`), and they exist
because two test files read `out/lambda/mainline-demo-api-arm64.zip`, a `.gitignore`'d build
output that lane does not build. **A lane that skips is indistinguishable from a green tick
on a dashboard**, which is the lane's own sentence and the reason it refuses instead of
reporting. The ceiling has not been raised and must not be; the fix is to build the package
in the lane. **This is a container on a runner, not CockroachDB Cloud** — nothing in this
repository has ever run a test suite against the managed cluster in CI, and the distinction
matters because a single node never returns `40001 RETRY_SERIALIZABLE` and a multi-node
Cloud cluster does.

### The exhibit: three beats, one committed transcript

`scripts/proof/gate_refusal.py` builds a schema, replays illegal histories, and writes
[`evidence/gate-refusal/proof-20260810T004200Z.json`](../evidence/gate-refusal/proof-20260810T004200Z.json).

| beat | outcome | SQLSTATE | exhibit |
|---|---|---|---|
| plain CHECK | REFUSED | `23514` [src: evidence/gate-refusal/proof-20260810T004200Z.json#refusal.sqlstate] | `gate_closed_when_issued`, source `reported` |
| **forged projection** | REFUSED | `P0001` [src: evidence/gate-refusal/proof-20260810T004200Z.json#drift_refusal.sqlstate] | `mainline.fn_permit_merge_gate`, source `parsed` |
| after one signed disposition | ADMITTED | `00000` [src: evidence/gate-refusal/proof-20260810T004200Z.json#admission.sqlstate] | `merge_record` with a server-computed clearance digest |

Verdict on the run: `PROVEN` [src: evidence/gate-refusal/proof-20260810T004200Z.json#verdict].

**The middle beat is the one to read twice.** The projected counter was set to zero out of
band — the exact attack a "materialised conflict" design must survive — and the gate
refused anyway, because it **re-derives** the obligation count instead of trusting the
column it is handed. P2 projections are enforced, never trusted. The third beat matters
just as much: a gate that always refuses is broken, not safe.

That run measured a tree of
261 [src: evidence/gate-refusal/proof-20260810T004200Z.json#chain.files] migration files
with 246 [src: evidence/gate-refusal/proof-20260810T004200Z.json#chain.applied_count]
applied and 15 [src: evidence/gate-refusal/proof-20260810T004200Z.json#chain.failed_count]
failing, every failure attributable to a named table with no producer migration and
0 [src: evidence/gate-refusal/proof-20260810T004200Z.json#chain.failures_unexplained|len]
failures unexplained. **That is a snapshot of `2026-08-10T00:42:10Z`, not a statement about
the tree today** — the tree now holds
271 [src: evidence/tool-usage/crdb-features.json#scan.files_by_category.migration]
migration files, and re-running the proof is the only honest way to update those three
numbers.

### The engine features, and what each one is doing here

| feature | verdict | files | anchor |
|---|---|---|---|
| SERIALIZABLE isolation | EXERCISED | 263 [src: evidence/tool-usage/crdb-features.json#rows.crdb_serializable.file_count] | `packages/trappoint-model/src/trappoint_model/cluster.py:222` |
| PL/pgSQL triggers & functions | EXERCISED | 128 [src: evidence/tool-usage/crdb-features.json#rows.crdb_triggers.file_count] | `verticals/mainline/db/migrations/0115_fn_permit_merge_gate.sql:77` |
| Named CHECK constraints | EXERCISED | 330 [src: evidence/tool-usage/crdb-features.json#rows.crdb_check_constraints.file_count] | `verticals/mainline/db/migrations/0050_permit.sql:114` |
| C-SPANN vector index | EXERCISED | 160 [src: evidence/tool-usage/crdb-features.json#rows.crdb_vector_index.file_count] | `verticals/mainline/db/migrations/0031_clause_embedding.sql:149` |
| `AS OF SYSTEM TIME` | EXERCISED | 85 [src: evidence/tool-usage/crdb-features.json#rows.crdb_as_of_system_time.file_count] | `packages/trappoint-conformance/cases/cf46_time_travel_cannot_reach.py:106` |
| Follower reads | EXERCISED | 13 [src: evidence/tool-usage/crdb-features.json#rows.crdb_follower_reads.file_count] | `verticals/mainline/db/migrations/0180c_role_agent_patroller.sql:37` |
| Row-level security | EXERCISED | 46 [src: evidence/tool-usage/crdb-features.json#rows.crdb_row_level_security.file_count] | `verticals/mainline/db/migrations/0181a_permit_rls_force.sql:54` |
| `SHOW CREATE` self-attestation | EXERCISED | 71 [src: evidence/tool-usage/crdb-features.json#rows.crdb_show_create.file_count] | `packages/trappoint-migrate/src/trappoint_migrate/attest.py:243` |
| `crdb_internal` | EXERCISED | 89 [src: evidence/tool-usage/crdb-features.json#rows.crdb_internal.file_count] | `packages/mainline-mcp/src/mainline_mcp/limits.py:75` |
| CHANGEFEED / CDC | **DESIGNED** | 7 [src: evidence/tool-usage/crdb-features.json#rows.crdb_changefeed.file_count] | `verticals/mainline/db/migrations/0168_v_changefeed_health.sql:37` |

Now the *how*, which is the part the rule actually asks for.

#### SERIALIZABLE — because the gate reads before it writes

`verticals/mainline/db/migrations/0115_fn_permit_merge_gate.sql:56` reads the projected
counter, re-derives the true count, and then permits or refuses a write. Under anything
weaker than SERIALIZABLE that read-then-write pair is a write-skew hole, and the whole
safety claim leaks through it. So isolation is **set explicitly on the connection**
(`packages/trappoint-model/src/trappoint_model/cluster.py:222`) rather than inherited as a
default that a future cluster setting could change underneath us, and the conformance
harness retries `40001` and nothing else
(`packages/trappoint-conformance/src/trappoint_conformance/sqlstate.py:38`) — a blanket
retry helper is a forbidden import repo-wide, because retrying a constraint violation is
how a refusal becomes a delay.

*Re-measured on the pinned local node 2026-08-12:* `SHOW default_transaction_isolation` →
`serializable`, on `CockroachDB CCL v26.2.5`.

The write-skew pair below is **from the earlier run and was not re-executed on 2026-08-12** —
the shared local node was carrying enough concurrent work from other scratch databases that
the two-session probe did not complete inside a `12 s` statement timeout. That is a
statement about the node's load, not about the claim, and it is recorded here rather than
quietly presented as fresh. What was re-confirmed today is the isolation level; what is
quoted below is dated:

```
A: BEGIN; SELECT sum(v) FROM ledger        -> 20
B: BEGIN; SELECT sum(v) FROM ledger        -> 20
A: UPDATE ledger SET v = 0 WHERE k = 1
B: UPDATE ledger SET v = 0 WHERE k = 2
A: COMMIT                                  -> ok
B: COMMIT                                  -> 40001 restart transaction:
                                              TransactionRetryWithProtoRefreshError
```

Two transactions reading an aggregate and each writing a different row is the textbook
anomaly the gate would be exposed to. The database refused it.

#### Triggers and PL/pgSQL — the gate is in the database, not in front of it

`verticals/mainline/db/migrations/0115_fn_permit_merge_gate.sql:77` is the `RAISE EXCEPTION USING ERRCODE = 'P0001'` that
produced the second beat of the proof; `verticals/mainline/db/migrations/0120_trg_check_project.sql:28` is the `BEFORE
INSERT` trigger that projects a cross-row fact onto a scalar column. Triggers are a v26.2
feature and the design depends on them existing: without them the projection would have to
be maintained by the application, which is the failure mode the product exists to remove.

One platform detail worth publishing because it cost real time:
`verticals/mainline/db/migrations/0115_fn_permit_merge_gate.sql:54` notes that the unparenthesised `NEW.col` read form does
not survive `CREATE TRIGGER` on v26.2.5, so every trigger body assigns `(NEW).col` to a
local first.

#### Named CHECK constraints — the constraint *name* is the deliverable

`verticals/mainline/db/migrations/0050_permit.sql:114`:

```sql
CONSTRAINT gate_closed_when_issued CHECK (state <> 'merged' OR open_blocking = 0),
```

A refusal with the right SQLSTATE and the wrong constraint name is the right outcome for
the wrong reason, so every conformance case asserts **both**, and the proof records
`constraint_source` as `reported` or `parsed` — `parsed` when the driver gave no
`diag.constraint_name` and the exhibit had to be recovered from the message, which is
always the case for `P0001`. Saying which is the difference between a diagnosis and a
guess.

#### C-SPANN vector index — recall and refusal in one transaction domain

`verticals/mainline/db/migrations/0031_clause_embedding.sql:149`:

```sql
VECTOR INDEX ce_ann (site_id, activity_root, embedding vector_cosine_ops),
```

Declared **inline at `CREATE TABLE`**, because on v26.2 building a vector index over an
already-populated table is the slow path; the table is created empty and loaded after.
Vectors live in sidecar tables, one embedding space each, because a table may carry only
one vector index.

*Re-measured on the pinned local node 2026-08-12*, `500` rows in a table of this exact shape
in scratch database `w_w6_tool_usage`:

```
EXPLAIN … ORDER BY embedding <=> … LIMIT 5      →  • scan
                                                     table: ce@ce_pkey
                                                     spans: FULL SCAN
EXPLAIN … FROM ce@ce_ann WHERE site=… AND       →  • vector search
             root=… ORDER BY … LIMIT 5                table: ce@ce_ann
                                                      prefix spans: [/'s1'/'hot-work'
                                                                   - /'s1'/'hot-work']
```

Note what differs between those two statements: it is **not only the hint**. The first also
leaves the prefix columns unconstrained. Read as a hint-versus-no-hint comparison it is not a
controlled one, and we published it as such for ten days.

**Corrected 2026-08-18.** A controlled sweep — same filters, hint removed, row counts 0, 200,
1,100 and 5,300 — shows the optimizer choosing `ce_ann` **without being asked**, at every size
including the 5,200 our earlier note named. The claim *"the index is chosen only when explicitly
hinted"* is **struck**, not softened: [`docs/upstream/STRIKE-LEDGER.md`](upstream/STRIKE-LEDGER.md)
§2, finding F03. The artefact we had cited as its proof,
[`evidence/aws/ann/explain-unhinted.txt`](../evidence/aws/ann/explain-unhinted.txt), records the
refutation in its own body.

**What survives, and is the load-bearing half:** the index is traversed when every prefix column
is pinned to a single value, and a declared `FULL SCAN` is the failure mode worth naming, because
an ANN query that silently degrades to one returns plausible rows and hides a design error behind
them. So the recall path pins the prefix, keeps the hint as belt-and-braces, and asserts the plan
rather than trusting it —
`skills/designing-vector-recall-prefixes/scripts/assert_prefix_index_used.py` exists to fail when
the plan stops using the index.

#### `AS OF SYSTEM TIME` and follower reads — including where they stop

Two uses, and the second is the interesting one.

*Operationally*: fixity patrol and coverage scans read at `follower_read_timestamp()`
(`verticals/mainline/db/migrations/0180c_role_agent_patroller.sql:37`) so a background integrity sweep never contends with
a merge, and a patrol run that cannot state its follower-read timestamp is refused by its
own emitter.

*Epistemically*: `AS OF SYSTEM TIME` is **not** sold as "prove the state at time T".
`packages/trappoint-conformance/cases/cf46_time_travel_cannot_reach.py:106` is a
conformance case whose whole purpose is to show it cannot. The GC window on this cluster
is 4500 [src: evidence/gate-refusal/proof-20260810T004200Z.json#cluster.zone.gc_ttlseconds]
seconds — pinned locally to the Cloud value, so local is never more permissive than
production — and a query past it is **refused**, not silently answered from a truncated
history. Long-horizon reconstruction is the application-level commit DAG instead.

*Measured on the pinned local node 2026-08-12.* `SELECT follower_read_timestamp()` returns
(`2026-08-12 15:15:41.321012`); `ALTER DATABASE … CONFIGURE ZONE USING gc.ttlseconds = 4500`
applies and `SHOW ZONE CONFIGURATION` reads it back. And the far-past read is refused:

*Re-measured 2026-08-12 in scratch database `w_w6_tool_usage`*, and it corrected two things
this document used to say:

```
SELECT count(*) FROM system.namespace AS OF SYSTEM TIME '-90m'    -> 1619 rows
SELECT count(*) FROM system.namespace AS OF SYSTEM TIME '-2160h'  -> XXUUU
    "error in retrieving descs between …: batch timestamp 1778771745… must be
     after replica GC threshold 1786454413… (r7: /Table/{0-4})"
```

An earlier version quoted `3658` rows and the message *"found no descriptor with id 1"*.
**The SQLSTATE `XXUUU` reproduced exactly; the other two did not.** The row count is a live
cluster's count on a particular day and was never going to reproduce. The message text on
this node names the GC threshold directly, which is the *better* exhibit — it says which
boundary was crossed rather than reporting the symptom downstream of it.

*That distinction was itself a correction made mid-measurement, and it is worth admitting.*
The `cockroach sql` client printed the refusal without a SQLSTATE, and a first pass through
this block wrote that `XXUUU` no longer held. A second run through `psycopg`, which surfaces
`sqlstate` on the exception, showed `XXUUU` intact. **Two tools, two different views of the
same refusal, and the less informative one nearly put a false correction into a public
document.** Every SQLSTATE quoted in this file is read from a driver's `sqlstate` field, not
from a rendered error string.

**One more thing that changed and strengthens the section below.** `system.namespace` is
itself now behind `allow_unsafe_internals` on `v26.2.5`: without it, the `-90m` read above
is refused `42501` *"Access to `crdb_internal` and `system` is restricted"*. The
restriction is not `crdb_internal`-specific.

**Read the pair precisely.** What it shows is that a read far enough into the past is
refused rather than answered from a truncated history. It does **not** demonstrate the
`4500`-second boundary specifically — that is conformance case CF-46, and the conformance
suite is in **Part 4 · What is NOT claimed**.

#### Row-level security — FORCE, and no session variables

`verticals/mainline/db/migrations/0181_permit_rls_enable.sql:51` enables it;
`verticals/mainline/db/migrations/0181a_permit_rls_force.sql:54` **forces** it, so table owners are not exempt.
Policy expressions carry no subquery and no session variable — a session variable is client-settable, which would degrade RLS to an
application-cooperative control against exactly the adversary it is meant to constrain —
so the documented-safe shape is `USING (col = CURRENT_USER)` over a denormalised role
token.

The trap that this design has to survive is that with `FORCE` and SELECT-only policies the
default is DENY and **the gate locks itself out**, so every RLS-forced table a trigger
writes carries an explicit write policy. RLS is never enabled on the CDC source tables,
because changefeed queries fail on RLS-enabled and multi-family tables
(`verticals/mainline/db/migrations/0198x_no_rls_on_cdc_sources.sql`).

*Measured on the pinned local node:* after `ENABLE` + `FORCE` + one policy,
`pg_class.relrowsecurity` and `relforcerowsecurity` are both true and `pg_policy` holds
`('standing_owner_read', 'r', 'owner = current_user()')`.

#### `SHOW CREATE` — so the gate cannot be quietly edited

`packages/trappoint-migrate/src/trappoint_migrate/attest.py:243` fingerprints the live
schema from `SHOW CREATE ALL SCHEMAS / TYPES / TABLES` plus `pg_get_triggerdef()` and
`pg_get_functiondef()`, normalises (sort, collapse whitespace — intra-category ordering is
not guaranteed), hashes, and chains the hash into `trappoint.schema_attestation`. The
gate's **own source text** is therefore inside the attestation. `SHOW CREATE ALL TABLES`
omits routines, which is exactly why the `pg_get_*def()` half is there and why a fallback
to `SHOW CREATE TABLE` records `attestation_grade="weak"` in the row rather than pretending
equivalence.

*Measured on the pinned local node:* `SHOW CREATE TABLE` returned DDL naming the vector
index `ce_ann`.

#### `crdb_internal` — used by us, forbidden to the auditor

Two opposite uses, and the second is a security property.

*Internally*, `cluster_logical_timestamp()` is the HLC the sequencer orders appends by,
because `CREATE SEQUENCE` / `nextval` / `SERIAL` / `unique_rowid()` are banned repo-wide
(ADR `0045`). *Externally*, `crdb_internal` is on the MCP identity's forbidden list at
`packages/mainline-mcp/src/mainline_mcp/limits.py:75`, alongside `pg_catalog`,
`information_schema` and `pg_extension`. That it is **unreachable** over the audit surface
is what proves the `mainline_audit` views *are* the API rather than a bypass around one.

*Measured on the pinned local node, and it corrects two things worth publishing.*

```
SELECT count(*) FROM crdb_internal.tables            -> 42501 "Access to crdb_internal
                                                        and system is restricted"
SELECT crdb_internal.cluster_logical_timestamp()     -> 42883 "unknown function:
                                                        crdb_internal.cluster_
                                                        logical_timestamp()"
SELECT cluster_logical_timestamp()                   -> 1786547745553893701.00
```

*Re-measured 2026-08-12; the two SQLSTATEs and the bare builtin all reproduced.* The
`cluster_logical_timestamp()` value is a clock reading and differs on every run by design —
it is shown for shape, not as a figure to check.

An earlier version of this block also reported *"`SET allow_unsafe_internals = true`; same
query → `5642` rows"*. **The row count is deleted rather than refreshed.** It is a count of
descriptors across every database on the node, so it moves whenever anyone creates a scratch
database, and on a shared node it is not a property of CockroachDB at all — it is a property
of who else was working that afternoon. The *opt-in* is the claim and it stands; the number
attached to it never should have been.

First: on `v26.2.5` `crdb_internal` is **restricted by default**, and reaching it requires
opting in with `allow_unsafe_internals`. So the unreachability this design leans on is a
**platform default before it is a policy of ours** — which strengthens the claim rather
than weakening it. Second: the qualified spelling
`crdb_internal.cluster_logical_timestamp()` does not exist on this version; the builtin is
unqualified. `docs/adr/0045-cas-sequencing-not-sequences.md:142` uses the qualified form —
recorded here as a cross-domain note, and **not** edited, because that file is not this
document's to touch.

#### CHANGEFEED — DESIGNED, and deliberately not in a migration

`CREATE CHANGEFEED` appears in
7 [src: evidence/tool-usage/crdb-features.json#rows.crdb_changefeed.file_count] files and
has never been run. *Re-measured on the pinned local node 2026-08-12:* `SHOW CHANGEFEED
JOBS` → `0` jobs, and `SHOW CLUSTER SETTING kv.rangefeed.enabled` → **`false`**.

**That second value is a correction, and it makes this row weaker in the honest direction.**
This document previously reported `true` and described the machinery as "present and idle".
On this node today CDC is not merely unstarted — it is **not currently startable** without
flipping a cluster setting first. `DESIGNED` was already the verdict; this is what
`DESIGNED` actually looks like when you go and check, and a reader who runs `just up` and
the command above will see `false` too rather than wondering which of us is wrong.

That is a design decision before it is a gap: putting `CREATE CHANGEFEED` in a migration
makes migrations non-idempotent across a restore, so CDC is owned by the provisioning
agent, and the two migrations that exist —
`verticals/mainline/db/migrations/0155a_ops_changefeed_health_snapshot.sql` and
`verticals/mainline/db/migrations/0168_v_changefeed_health.sql:37` — observe changefeed health rather than start a
feed. The single CDC source table is `mainline_ops.outbox`, which is why RLS is forbidden
on it.

---

## Tool 2 · CockroachDB Cloud and the `ccloud` CLI — EXERCISED

**Verdict: EXERCISED.** [`evidence/ccloud/cluster-list.txt`](../evidence/ccloud/cluster-list.txt)
is a verbatim captured transcript of `ccloud auth whoami` followed by
`ccloud cluster list -o json`, ANSI spinner frames stripped and nothing else altered. The
term appears in 77 [src: evidence/tool-usage/crdb-features.json#rows.crdb_cloud_ccloud.file_count]
files across the tree.

```json
{ "name": "mainline-dev", "cockroach_version": "v26.2.5", "plan": "SERVERLESS",
  "cloud_provider": "AWS", "regions": [{ "name": "ap-southeast-1", "primary": true }],
  "config": { "serverless": { "spend_limit": 2500,
    "usage_limits": { "request_unit_limit": "100000000", "storage_mib_limit": "10240" }}}}
```

**How, specifically.** `-o json` is the point: the CLI is driven with structured output and
the JSON is **parsed, never screen-scraped**. `spend_limit: 2500` is the US$25.00 monthly
cap set at cluster creation — a ceiling, not a spend.

### Two measured limitations, published rather than worked around

**1 · `ccloud` 0.6.12 has no headless service-account authentication.**
`evidence/ccloud/README.md:37`. `ccloud auth` exposes only `login` / `logout` / `whoami`;
`login` is browser-based; `CC_API_KEY` in the environment is ignored; the cached session is
scoped to the interactive Windows logon and is not readable from a non-interactive shell.
`0.7.0`, `0.8.0`, `0.9.0` and `1.0.0` all `404` from `binaries.cockroachdb.com`, so
`0.6.12` is the latest published build.

**Therefore an agent cannot drive `ccloud` headlessly from a cold start, and MAINLINE does
not claim that it does.** Headless paths use the **CockroachDB Cloud REST API** with the
same service-account key, verified live against `/clusters`, `/clusters/{id}`,
`/service-accounts`, `/api-keys` and `/clusters/{id}/sql-users`.

**2 · Audit-log endpoints `404` on this tier.** `evidence/ccloud/README.md:46`.
`/auditlogentries`, `/auditlogs`, `/audit-logs` and the cluster-scoped variant all return
`404` on Basic/Serverless. The custody design's *"custody of the custodian"* mechanism —
folding control-plane audit records into the tamper-evident ledger — therefore has **no
input source on this tier**, and is documented as unavailable rather than shipped as an
unbacked claim.

### What the managed cluster now carries, added 2026-08-14 — and what it still does not

This row was already EXERCISED on the strength of the `ccloud` transcript alone, so nothing
below is a promotion; it is the **evidence behind an existing verdict getting stronger**, and
it is dated so that a reader can tell the two apart.

> **CockroachDB Cloud carries the demo world, and the gate refuses there.** The migration chain
> is `APPLIED` and the seeded world is `SEEDED AND REFUSABLE` against
> `mainline-dev-31219.j77.aws-ap-southeast-1.cockroachlabs.cloud`, database `mainline_demo`,
> CockroachDB CCL v26.2.5 — the refusal observed on Cloud is `23514`
> `gate_closed_when_issued`, with `nothing_persisted: true`
> [src: `evidence/deploy/cloud-chain.json#outcome`, `evidence/deploy/cloud-seed.json#verdict`,
> `#verification`].
>
**And the second half of that ruling, which this page states rather than quotes.** The
four-beat run through the HTTP handler has **not** been recorded against Cloud: it is reported
in the body of commit `7535670`, whose diff carries no such artefact, and `evidence/` holds
none. It is **OWED**, and until the run exists the only `PROVEN` this repository holds is
[`evidence/gate-refusal/proof-20260814T032418Z.json`](../evidence/gate-refusal/proof-20260814T032418Z.json),
which is **local** (`cluster.database = w_qr_gate_refusal_proof`).

The ruling names the filename that owed artefact will be written to, and **this page does not
repeat it**, on purpose: every `evidence/….json` string on this page is read as a citation by
`scripts/submission/check_submission_ready.py`, which counts how many of them a reader can
actually open. Typing the name of a file that does not exist would turn *"21 of 21 cited
artefacts present"* into *"24 of 25"* — a citation that is a path somebody typed rather than a
file a reader can open, which is precisely what that check exists to refuse. The exact words,
filename included, are carried verbatim in `docs/leads/docs-true-final.md` RULING 1 and in
`docs/STATE-OF-THE-BUILD.md`, `docs/HONESTY.md`, `docs/CI-STATE.md` and
[`docs/submission/JUDGING-AXES.md`](submission/JUDGING-AXES.md) §2, none of which is under
that counting rule.

**And the harder half, stated on the same page as the good news:
nothing has ever run against CockroachDB *Cloud* in CI.** The lane that starts a database
starts a pinned `cockroachdb/cockroach:v26.2.5` **container** on the runner — a real database,
not the managed one — and the difference is load-bearing, because a single node never returns
`40001 RETRY_SERIALIZABLE` and a multi-node Cloud cluster does.

---

## Tool 3 · CockroachDB Managed MCP Server — **EXERCISED**, promoted 2026-08-12, surface re-measured 2026-08-16

**Endpoint** `https://cockroachlabs.cloud/mcp`, MCP **Streamable HTTP**, `Authorization:
Bearer <service-account key>`, and an `mcp-cluster-id` header pinning exactly one cluster —
a tool call naming a different cluster fails. All three constants are code, not prose:
`packages/mainline-mcp/src/mainline_mcp/limits.py:45` and `:48`.

**Verdict: EXERCISED — and the promotion is dated, because a verdict that changes silently
is worth nothing.** Until 2026-08-12 this row read DESIGNED on the basis *"no live session
against the managed endpoint is captured in `evidence/`"*. That stopped being true on
2026-08-11 and the census had not been re-run, so for one day the document argued with
itself in two places. [`evidence/deploy/judge-run.json`](../evidence/deploy/judge-run.json)
records an MCP session against `https://cockroachlabs.cloud/mcp` — protocol
`2025-06-18`, server `cockroachdb-cloud` `1.0.0`, `tools/list` returning `12` tools — driving
the whole 16 [src: evidence/deploy/judge-run.json#questions] question judge pack over that
channel against the live Basic cluster `7cfc9ee9-f9b4-413d-bcad-d81fca2c6c7e`:
15 [src: evidence/deploy/judge-run.json#channels.mcp.passed] PASS of
16 [src: evidence/deploy/judge-run.json#channels.mcp.total].

**The one FAIL is not rounded off, and the run's own verdict is `DIVERGED — KNOWN GAP`.**
`N01`: the `managed-mcp` identity *can* read `mainline_qa.v_disposition_profile`, which the
pack's envelope asserted it could not. That is a real gap in the negative half of the
reachability model, recorded as a gap. The run also settles two questions `FALLBACK.md` had
left open pessimistically — the endpoint runs as the SQL user `managed-mcp`, not `root` and
not the database owner — and one it had left open optimistically: the MCP credential is
**not publishable to anonymous judges**, so this channel cannot be the judge access path.

### Re-taken 2026-08-16 — and the primary artefact is now `evidence/mcp/`

**The two `evidence/deploy/` files cited above are not superseded, not moved and not
replaced.** They are the 2026-08-11 transcript; they are cited from this page, from
[`docs/demo/ON-SCREEN-CLAIMS.md`](demo/ON-SCREEN-CLAIMS.md) and from
[`MCP-CONFIG.md`](../verticals/mainline/demo/judge/MCP-CONFIG.md), and every citation to them
on this page still lands. [`evidence/mcp/`](../evidence/mcp/README.md) is **additive**: it is
where a judge looking for *the MCP tool* will actually look, which is the defect it closes —
the older transcript is filed under a directory whose name says *deployment*.

**And the 2026-08-11 record is now legible from inside that directory too, as a copy that says
on its own face that it is one.**
[`evidence/mcp/session-extract.json`](../evidence/mcp/session-extract.json) reproduces the
`channels.mcp` and `managed_mcp_availability` blocks of
[`evidence/deploy/judge-run.json`](../evidence/deploy/judge-run.json) unaltered — key order
preserved, no value edited — inside an envelope carrying the source path, the source file's
SHA-256 `851a0e1c…a9b6e4ec`, and the words *copied, not re-run*. **No MCP call, no network
request and no credential read produced it**, and that is the whole of its provenance. It
earns its place by making one comparison checkable without leaving the directory: the
`15`-of-`16` and the single divergence `N01` that **both** captures report — the four figures
already cited above, off `judge-run.json#channels.mcp.passed` / `.total` and
`pack-run.json#passed` / `#total` — sit side by side in its
`why_this_copy_is_worth_keeping` block, each labelled with the client that produced it. The block also states what the agreement does
*not* show: both runs used the same key against the same cluster, so a fault in that
identity's grants reproduces in both — and `N01` is exactly such a fault. Check the copy
against its source in one command, no credential and no network:

```bash
python -c "import json,hashlib; s=json.load(open('evidence/deploy/judge-run.json')); e=json.load(open('evidence/mcp/session-extract.json')); print(e['extract']['channels.mcp']==s['channels']['mcp'], e['extract']['managed_mcp_availability']==s['managed_mcp_availability'], hashlib.sha256(open('evidence/deploy/judge-run.json','rb').read()).hexdigest()==e['source']['sha256'])"
#  ->  True True True
```

**Both caveats ride with that copy, as they ride with every MCP sentence on this page.** The
run it reproduces carries the verdict **`DIVERGED — KNOWN GAP`** for divergence `N01`, where
the `managed-mcp` identity **can** read `mainline_qa.v_disposition_profile` although the
pack's envelope asserted it could not. And the credential that reaches this endpoint is the
account's Cloud service-account key, which is **not publishable to anonymous judges** — so
Managed MCP is *demonstrated*, and it is **not** the judge access path. That path is the
read-only `mainline_judge` SQL login, whose reach is the fourteen `mainline_audit` views and
nothing else.

Taken on 2026-08-16 against the same Basic cluster, **read verbs only**, and it adds four
things the 2026-08-11 pass did not have:

| what was taken | artefact | what it adds |
|---|---|---|
| the handshake and the SQL identity | [`evidence/mcp/session.json`](../evidence/mcp/session.json) | `protocolVersion 2025-06-18`, `serverInfo cockroachdb-cloud 1.0.0`, HTTP `200`, and `sql_identity` `managed-mcp` re-read on the day of submission rather than remembered |
| the twelve tools **with their full `inputSchema`** | [`evidence/mcp/tools-schema.json`](../evidence/mcp/tools-schema.json) | the argument names as the server declares them — the section below — plus a divergence block *derived from the schemas in the same file* rather than asserted |
| the sixteen-question pack, driven through **the pack's own runner** | [`evidence/mcp/pack-run.json`](../evidence/mcp/pack-run.json) | `python verticals/mainline/demo/judge/cli.py run --via mcp` → `runner.run_via_mcp`, so the envelope validator, the migration drift check and the 25-row truncation guard are all in the path. **The 2026-08-11 transcript carried none of the three** — it came from a 40-line ad-hoc client inside `scripts/deploy/judge_access.py` |
| a general-counsel persona and a byte-budget prober, **live** | [`evidence/mcp/auditor-live.json`](../evidence/mcp/auditor-live.json), [`evidence/mcp/budget-live.json`](../evidence/mcp/budget-live.json) | both modules were previously proven only against a constructed transport. Ten questions routed deterministically to contracted views, and 13 [src: evidence/mcp/budget-live.json#verdict.views_measured] views measured on the wire |

**The fresh pack run returns the same arithmetic as the old one, and that is the point.**
15 [src: evidence/mcp/pack-run.json#passed] PASS of
16 [src: evidence/mcp/pack-run.json#total], verdict `DIVERGED — KNOWN GAP`, the same single
divergence `N01`. Five days, a different client, a stricter validator, and the number did not
move — which is worth more than a fresh green would have been. Only two verbs were used,
`select_query` and `explain_query`; no write verb was called, and the capture program enforces
that at the transport rather than promising it.

**Read the budget verdict with its own caveat, which the artefact prints beside it.** All
13 [src: evidence/mcp/budget-live.json#verdict.views_measured] views measured came in under
budget and 0 [src: evidence/mcp/budget-live.json#verdict.views_breached] breached — but
8 [src: evidence/mcp/budget-live.json#verdict.how_much_this_green_actually_proves.views_that_returned_zero_rows]
of them **returned no rows**, and a zero-row view costs `110` bytes because it is an empty
envelope. Its green proves the view is *reachable* and its statement *accepted*; it does not
prove the view stays inside `8192` bytes with data in it. The verdict that carries weight is
over the 5 [src: evidence/mcp/budget-live.json#verdict.how_much_this_green_actually_proves.views_that_returned_any_rows]
views that returned rows, and the largest of those was
517 [src: evidence/mcp/budget-live.json#verdict.largest_response.response_bytes] bytes.

And one answer worth quoting, because it is the demonstration rather than a description of
one: over the live endpoint, `mainline_audit.v_open_gate_summary` returned a single row with
`open_blocking = 1` — **a general-counsel question, *what is the gate refusing right now?*,
answered by CockroachDB's own managed endpoint out of a contracted view, with none of
MAINLINE's code in the read path.** The companion question — *which weakenings over severe
blame ancestry were never answered for?* — returned **no rows**, and the artefact records its
completeness as `vacuous` rather than as a clean bill of health: zero rows and
zero-findings-verified-complete are different facts, and only the first one was measured.

### The argument names — MEASURED 2026-08-16 from the server's own `inputSchema`

**This is the correction that matters on this page, and it is a correction to *us*.** Until
2026-08-16 the argument names in this repository were *our best reading of the documented
surface* — prose, interpreted, never put against the wire. On 2026-08-16 they were taken
instead from the `inputSchema` the server itself returns in `tools/list`, which is a stronger
source than either our reading or any published document, because it is the thing the server
validates against. Quoted from that response, recorded in
[`evidence/mcp/tools-schema.json`](../evidence/mcp/tools-schema.json):

```
select_query   required: ["database","query"]
   query        "The SQL query to execute (SELECT statements only). Use LIMIT/OFFSET in
                 your query for pagination."
   cluster_id   "Required when the MCP config has no cluster_id; otherwise must be omitted."
explain_query  required: ["database","query"]
insert_rows    required: ["database","query"]
```

Four readings, and the third and fourth are the ones a reader should not skip:

1. **The statement goes under `query`, and `database` is mandatory.** All three SQL verbs
   declare exactly `["database","query"]`. This package shipped `statement=` until
   2026-08-16; the name lived in a single injectable `ToolDialect` object precisely so a
   live-surface difference would be one field rather than seven hidden guesses, and it was.
   The superseded names are **kept, named and asserted against** in that module rather than
   erased, so the repository cannot quietly delete a guess it published.
2. **`cluster_id` is optional and, when the configuration pins a cluster in the
   `mcp-cluster-id` header, must be *omitted*** — its own description says so.
3. **`select_query` has no `limit` argument at all.** Pagination is `LIMIT`/`OFFSET` inside
   the statement. Our row ceiling is therefore ours, enforced client-side, and not a
   parameter of the server's; `limit` is a real property of `list_databases` and
   `list_tables` only.
4. **`insert_rows` takes a whole INSERT statement, not a `{table, rows}` pair** — and that
   one is **not corrected, on purpose**. See the write surface below.

The negative that pins the whole reading is the call that fails:

```
select_query {"database":"mainline_demo","statement":"SELECT 1 AS one"}
   ->  {"code": 0, "message": "must contain exactly one statement"}
```

That message is misleading about its own cause — the statement is well-formed and there is
exactly one of it. The server is reporting that the `query` property was **absent**, and the
count it complains about is a count of zero. The field-by-field version, and what to type
instead, is [`MCP-CONFIG.md`](../verticals/mainline/demo/judge/MCP-CONFIG.md) §1.2.

**What did *not* change with the promotion, restated with the 2026-08-16 measurement beside
it.** `tests/integration/mcp` still *skips with a reason* when no key is present rather than
passing vacuously, and **that is still the pass CI runs**: with no credential in the
environment, `69` tests collect and all `69` skip, each carrying the reason its own fixture
writes. A green audit-surface run with nothing to talk to asserts nothing, and a green
*negative* run with nothing to talk to asserts the opposite of what it claims. What is new is
that on 2026-08-16 the same three suites were also run **with** a credential, and that census
is committed at [`qa/mcp-live.json`](../qa/mcp-live.json): `69` collected, `51` passed, `17`
skipped, **`1` failed**. The one failure is `N01` — the same gap, failing loudly, with the
gap's name in its message. **It is not on the repository's tracked baseline** (`SUITE_PATHS`
is `verticals/mainline/apps/demo-api/tests` and `tests/deploy`, and `tests/integration/mcp` is
in neither), and it is recorded rather than made green.

The MCP-facing surface — the client plus the `mainline_audit` schema it reads — appears in
215 [src: evidence/tool-usage/crdb-features.json#rows.crdb_managed_mcp.file_count] files.

### How: every documented limit is a type, not a comment

`limits.py` models the server's caps so a breach is refused **client-side** with an error
naming the limit, instead of arriving later as a truncated string:

| limit | value | line |
|---|---|---|
| statements per call | `1` | `packages/mainline-mcp/src/mainline_mcp/limits.py:54` |
| statement length | `16384` chars | `packages/mainline-mcp/src/mainline_mcp/limits.py:51` |
| request timeout | `20` s | `packages/mainline-mcp/src/mainline_mcp/limits.py:57` |
| **response cap** | **`10240` bytes** | `packages/mainline-mcp/src/mainline_mcp/limits.py:60` |
| SELECT rows, default / max | `25` / `10000` | `packages/mainline-mcp/src/mainline_mcp/limits.py:63`, `:66` |
| our own budget | `8192` bytes / `25` rows | `packages/mainline-mcp/src/mainline_mcp/limits.py:109`, `:112` |

**The `10 KiB` cap is the load-bearing one, because the server truncates rather than
raising.** A truncated answer to *"how many recalled precursors went undispositioned?"* is
not a smaller answer — it is a **wrong** one, and it looks exactly like a right one. So the
contracted `mainline_audit` views are shaped aggregate-first to ≤`25` rows and measured at
≤`8192` bytes — `80 %` of the cap, deliberately, so that corpus growth breaches the budget
in CI
rather than in front of a judge.
`packages/mainline-mcp/src/mainline_mcp/budget.py` is the prober that measures actual
response bytes per view and records the worst observed row, and on 2026-08-16 it measured
13 [src: evidence/mcp/budget-live.json#verdict.views_measured] of them **on the wire**
rather than against a fixture.

**This page said `nine` here until 2026-08-16, and the number is corrected rather than
quietly refreshed, because the live capture is what caught it.** The contracted surface is
`ARCHITECTURE_VIEWS` at `packages/mainline-mcp/src/mainline_mcp/catalogue.py:49`, which
carries **thirteen** names; the budget prober measured all thirteen, which is why the figure
above and the figure in the section on the fresh capture are now the same number instead of
two numbers a reader has to reconcile. [`VERIFY.md`](../VERIFY.md) Tier 3 tabulates **nine**
of them with the question each answers. The four it does not name are
`v_gate_latency_daily`, `v_txn_restart_daily`, `v_unused_indexes` and `v_changefeed_health`
— every one of which returned **zero rows** in the live run, so the un-tabulated four are
also the four with the least to say. **`VERIFY.md` is not this document's to edit**, so the
shortfall is recorded here rather than closed by hand, exactly as the ADR `0045` note above
records a cross-domain correction without making it.

Two of the thirteen carry `ancestry_complete` — `v_weakenings_without_disposition` and
`v_disposition_coverage`, per the `truncation_flag` field on each measurement in
[`evidence/mcp/budget-live.json`](../evidence/mcp/budget-live.json). When it is false the
counts beneath are **lower bounds** and the view says so rather than rounding the problem
away.

### The negatives are the interesting half

`mainline_qa`, `crdb_internal`, `pg_catalog`, `information_schema` and `pg_extension` must
all be **unreachable**
(`packages/mainline-mcp/src/mainline_mcp/limits.py:75` and `:89`), and `insert_rows` must be
rejected on every table except `mainline_meas.external_attestation`
(`packages/mainline-mcp/src/mainline_mcp/limits.py:101`) — a binding in the type, not a
runtime check. `tests/integration/mcp/test_negative_reachability.py` asserts these over the
live endpoint deliberately **bypassing our own client-side screen**, because a control that
lives only in our client is a control an attacker skips by not using our client.

**Re-read from the live server on 2026-08-16, in its own words rather than paraphrased**, and
identical to the 2026-08-11 transcript. Five schemas are refused **by the server, by name,
before SQL privilege is consulted** — `crdb_internal`, `information_schema`, `pg_catalog`,
`pg_extension` and `system`, each *"query references a restricted schema: access to `X` is
blocked for security reasons"*. That is a stronger guarantee than a grant, because no
privilege change on our side can weaken it. Two more refusals were measured the same day: a
`cluster_id` argument passed while the header pins the cluster returns *"cluster_id is set in
your MCP config; omit the cluster_id argument"*, and a cluster **name** in the header is
refused at `initialize` with HTTP `400`, *"must be a valid UUID"*.

**One trap in that list is worth publishing, because it nearly made a negative suite lie.**
Two statements in one call and the *superseded* `statement=` dialect return the **same
sentence** — `must contain exactly one statement`. A negative helper that accepted any error
would have recorded a wrong property name as a security refusal, which is a green that
asserts the opposite of what it claims. The suites now require a positive control before
believing anything they did not receive.

The single permitted write exists so a third party's agent can record the outcome of *its
own* verification into our log — their claim about our log, never our claim about the
world. Insert-only is an exact match for append-only archival memory, which is why it is
the only write surface there is.

**And the write verb is real, measured, and deliberately not in the demo's request path.**
`insert_rows` is on the live tool list and its measured shape is `{database, query}` — a whole
INSERT statement, with a table name inside it. Our `insert_external_attestation` sends
`{table, rows}`, and its published guarantee is that **no parameter of it names a table**:
"insert into something else" is not a call the supported API can express, which is a property
of the signature rather than a check at run time. Speaking the live shape means building SQL
inside that one method and trading the guarantee for a demonstration. **We did not make that
trade**, so the typed write verb is not sent over the live surface — it is real code with a
real suite against a constructed transport, the divergence is recorded in
[`evidence/mcp/tools-schema.json`](../evidence/mcp/tools-schema.json) rather than smoothed
over, and this sentence is the whole of the claim.

### The pessimistic assumption we published instead of guessing

Which SQL identity `select_query` runs as is undocumented. Rather than assume favourably,
`VERIFY.md` states that the MCP identity is treated as **admin-equivalent** and RLS is
assumed **not** to apply: every view on the surface is safe to read in full, `mainline_qa`
never receives an account on any tier, and MCP is never marketed as site-scoped.

---

## Tool 4 · CockroachDB Agent Skills — DESIGNED

Two authored skills plus one staged upstream contribution;
21 [src: evidence/tool-usage/crdb-features.json#rows.crdb_agent_skills.file_count] files
name them.

| skill | what it teaches | its executable assertion |
|---|---|---|
| `skills/designing-diachronic-gates/` | the PROJECT / PIN / REFUSE idiom — a trigger projecting a cross-row fact onto a scalar, a composite FK under `ON UPDATE RESTRICT` pinning a completed transition to an epoch, and a plain CHECK over that scalar | `skills/designing-diachronic-gates/scripts/assert_gate_refuses.py:57` — spins a throwaway node, replays an illegal history, and **fails unless the expected SQLSTATE and constraint name are raised** |
| `skills/designing-vector-recall-prefixes/` | C-SPANN prefix rules: one vector index per table, inline at create, every prefix column a single value, and the hint | `skills/designing-vector-recall-prefixes/scripts/assert_prefix_index_used.py` — **fails unless the plan actually chooses the index** |
| `skills/upstream/cockroachdb-resilience-and-disaster-recovery/verifying-a-restore-by-merkle-root/` | de-branded, staged for contribution back to Cockroach Labs | `skills/upstream/cockroachdb-resilience-and-disaster-recovery/verifying-a-restore-by-merkle-root/scripts/verify_restore_merkle_root.py` |

**Verdict: DESIGNED** — the skills and their scripts are on disk, and no run of either
script is captured under `evidence/`, so they are shipped and not yet evidenced.

The design point is the third column. A skill whose advice cannot be falsified is a blog
post; each of these ships a program that goes red when the guarantee stops holding. Both
also encode a *recovery* step most guidance omits: `P0001` carries no
`diag.constraint_name`, so the raising object has to be recovered from the message text,
and `skills/designing-diachronic-gates/scripts/assert_gate_refuses.py:57` is the regex that does it.

---

## Feedback on the CockroachDB AI tools — offered because the rules invite it

The submission requirements list *"feedback on the CockroachDB AI tools or features"* as
optional. We have unusually specific material, because every item below **changed how this
system is built** rather than being an opinion about it. Each names the artefact or the line
that establishes it, so none of it has to be taken on trust.

### 1 · The `10240`-byte MCP response cap **truncates rather than raising** — and two silent narrowings compose

This is the finding we would most like to see changed, and the one that shaped the schema.

`MAX_RESPONSE_BYTES = 10_240` at
`packages/mainline-mcp/src/mainline_mcp/limits.py:60` carries the docstring *"At or above
this the answer may have been TRUNCATED."* **A truncated answer to *"how many recalled
precursors went undispositioned?"* is not a smaller answer — it is a wrong one, and it is
byte-for-byte indistinguishable from a right one.** There is no flag in the response saying
the result was cut.

A second narrowing compounds it, and we only found this by reading the live `inputSchema`
on 2026-08-16 rather than the prose. `select_query` declares exactly three properties —
`cluster_id`, `database`, `query` — so **it has no `limit` argument at all**, and its own
description reads: *"Automatically adds LIMIT 25 if not specified. Maximum LIMIT is
10000."* Both statements are quoted from
[`evidence/mcp/tools-schema.json`](../evidence/mcp/tools-schema.json), which records the
server's full schemas verbatim. So an agent that asks an aggregate question and does not
itself count rows can be silently limited **and** silently truncated, and receives a
well-formed page that looks like a complete answer.

**What we did about it, since the platform will not tell us.** The contracted
`mainline_audit` views are shaped aggregate-first to our own budget of `8192` bytes —
`80 %` of the cap, at
`packages/mainline-mcp/src/mainline_mcp/limits.py:109` — so corpus growth breaches the
budget **in CI rather than in front of a judge**; and the judge pack's runner carries a
truncation guard (`verticals/mainline/demo/judge/runner.py:160`,
`_truncation_verdict`) that flags any result of *exactly* the page size as *possibly
truncated* instead of reporting the page as the whole answer. Neither of those is a
mitigation we would need if the response said so itself.

**The ask, concretely:** a `truncated: true` field on the response envelope, or an error
rather than a quiet cut. Either one converts a wrong answer into a handleable one. The
row-count default would be easier to reason about as an explicit, echoed value too.

### 2 · The SQL identity behind `select_query` is undocumented — which is how `N01` happened

Which SQL identity the Managed MCP Server runs as is not stated anywhere we could find, so
this repository published a **pessimistic assumption** instead of a guess: `VERIFY.md`
treats the MCP identity as admin-equivalent, assumes RLS does not apply, and never markets
MCP as site-scoped.

Measurement then settled it in two directions at once, and both are recorded.
[`evidence/deploy/judge-run.json`](../evidence/deploy/judge-run.json) establishes the good
news — the endpoint runs as the purpose-built SQL user `managed-mcp`, **not `root` and not
the database owner**. And it establishes the gap: **`N01`**, the one FAIL in `15` of `16`,
where the `managed-mcp` identity **can** read `mainline_qa.v_disposition_profile` although
the pack's envelope asserted it could not. The run's own verdict is left at
**`DIVERGED — KNOWN GAP`** rather than rounded off, and the fresh 2026-08-16 capture in
[`evidence/mcp/pack-run.json`](../evidence/mcp/pack-run.json) reproduces the same single
divergence with a stricter client.

**The ask:** publish the identity `select_query` executes as and the grants it holds. A
consumer cannot model the negative half of its own reachability — the half that says what an
agent *must not* reach — against an identity whose privileges are undocumented. Note that
the read-only `mainline_judge` pgwire login this submission actually publishes refuses the
same statement at SQLSTATE `42501`, so the credential a judge is handed is the tighter of
the two; that does not make `N01` a pass and it is not scored as one.

### 3 · One error message is misleading about its own cause

Sending the statement under the wrong property name returns:

```
select_query {"database":"mainline_demo","statement":"SELECT 1 AS one"}
   ->  {"code": 0, "message": "must contain exactly one statement"}
```

The statement is well-formed and there is exactly one of it. The server is reporting that
the **`query` property was absent**, and the count it complains about is a count of *zero*.
Worse for a test suite: **two statements in one call returns the same sentence**, so a
negative helper that accepted any error would record a wrong property name as a security
refusal — a green assertion that means the opposite of what it claims. **The ask:** name the
missing property. This one cost real time, and it is the reason the 2026-08-11 transcript
was driven by an ad-hoc client rather than by the pack's own runner.

### 4 · `ccloud 0.6.12` has no headless service-account authentication

The single largest blocker to an *agent* driving the CLI, recorded at
`evidence/ccloud/README.md:37`: `ccloud auth` exposes only `login` / `logout` / `whoami`,
`login` is browser-based, **`CC_API_KEY` in the environment is ignored**, and the cached
session is scoped to an interactive Windows logon. `0.7.0`, `0.8.0`, `0.9.0` and `1.0.0` all
`404` from `binaries.cockroachdb.com`. So an agent cannot drive `ccloud` headlessly from a
cold start, and this project does not claim that it does — headless paths use the Cloud REST
API with the same key. Separately, `/auditlogentries`, `/auditlogs`, `/audit-logs` and the
cluster-scoped variant all `404` on Basic, which leaves the *"custody of the custodian"*
design with no control-plane input source on this tier. **The ask:** honour `CC_API_KEY` for
non-interactive use.

### 5 · What we would keep exactly as it is

Feedback that is only complaints is not feedback. The Managed MCP Server's **server-side
schema blocklist is a better control than a grant**, and it should stay: `crdb_internal`,
`information_schema`, `pg_catalog`, `pg_extension` and `system` are each refused **by the
server, by name, before SQL privilege is consulted** — *"query references a restricted
schema: access to `X` is blocked for security reasons"*. That is stronger than anything we
could configure, because **no privilege change on our side can weaken it**, and it is the
half of the reachability model that measured clean on both runs. Pinning the cluster by the
`mcp-cluster-id` header rather than by URL is the right shape too: a cluster *name* in that
header is refused at `initialize` with HTTP `400`, *"must be a valid UUID"*.

**One thing this section does not do is launder a gap into a compliment.** The suites that
would exercise the negative half — `tests/integration/mcp` — still *skip with a reason* when
no key is present rather than passing vacuously, and that remains the pass CI runs; the
live-credential census is committed separately at [`qa/mcp-live.json`](../qa/mcp-live.json)
with its `1` failure, which is `N01` above, failing loudly with the gap's name in its
message. The detail is under *Tool 3*.

---

# Part 2 · AWS — twelve services

**The account number is not published here, and an earlier version of this line was wrong
to publish eight of its twelve digits.** An account id is not a credential, but it enables
cross-account enumeration, and a partial mask that leaks two thirds of the digits is a
smaller version of the same mistake rather than a different one. Every artefact under
`evidence/` passes through `scripts/aws/_common.py::redact`, which strips the account field
of an ARN structurally, and `scripts/aws/verify_evidence.py` re-scans the whole of
`evidence/` for the shape on every CI run. The IAM principal is published instead as a
SHA-256 of its unique id, so two artefacts can be shown to share an author without naming
one. Profile `mainline-dev`,
region **`ap-southeast-2`** for Bedrock and **`ap-southeast-1`** for the demo stack beside
the database.

Six rows are EXERCISED and the evidence for each is named in its own row — three of them
model and metric calls, three of them the applied demo stack. Five are DESIGNED because
**that half is still not deployed**: no evidence bucket, no signing key, no trail, no
distribution, no schedule rule. One is NOT-AVAILABLE because it does not exist in this
region and we checked. The `mechanism` column is the file and line that *does the thing* —
every one of them re-checked against the substring the row is about, not merely against the
file's length, most recently on 2026-08-15 when two of them had drifted and the generator
refused to write; the `evidence` column is what a reader opens to check that it did.

**The two Bedrock rows name an AWS request id.** That is the strongest single token in this
table, because a request id is a string **AWS minted and this repository could not have**.
Every other number here is one we computed; those are witnesses we did not author.

*Thirteen rows below, twelve services.* The `cohere.embed-v4` row is a **measured finding,
not a thirteenth service** — it is a model this project tried to use, was refused, and did
not adopt. Its files are counted inside the embeddings row, which is why its `files` cell is
empty; it appears on its own line because a refusal that changed a design decision belongs
where a reader will see it, not in a footnote.

**Why the submission gate says `10 AWS services` about this page and this heading says
twelve, and why neither number is being moved.** They count different things, and a reader who
runs both deserves the arithmetic rather than a silent reconciliation.
`python scripts/submission/check_submission_ready.py` holds a **fixed table of ten AWS service
names** — `AWS_SERVICES` at `scripts/submission/check_submission_ready.py:201` — and asks
which of those ten this document mentions; ten is therefore its ceiling, not a census, and it
reports `10` because this page names all ten. The census walks the tree and emits **one row per
distinct use**, so Bedrock appears three times — inference, embeddings and Rerank — and
`evidence/tool-usage/aws-services.json#totals.rows` is `12`. The same arithmetic explains the
gate's *"2 AWS service(s) marked as having run"* against this page's `3` EXERCISED rows: the
gate counts the name **Amazon Bedrock** once, and two of the three EXERCISED rows are Bedrock.
**The heading is derived from the census and stays at twelve**; changing it to ten would move
this document away from the artefact it is checked against in order to agree with an
instrument that is not measuring the same quantity, which is the one direction this repository
does not allow. The identical paragraph is in
[`docs/submission/RULES-MATRIX.md`](submission/RULES-MATRIX.md) §1, deliberately, because the
discrepancy is visible from either page.

> **Annotation, 2026-08-15, written beside that paragraph rather than inside it.** Its last
> reconciliation — *"the gate's `2 AWS service(s) marked as having run` against this page's
> `3` EXERCISED rows"* — was taken when the AWS census had `3` EXERCISED rows. It has
> 6 [src: evidence/tool-usage/aws-services.json#totals.by_verdict.EXERCISED] now, and the
> gate re-run on 2026-08-15 prints *"`5` AWS service(s) marked as having run (Amazon Bedrock,
> Amazon CloudWatch, AWS Lambda, AWS IAM, AWS SSM Parameter Store); `28` of `28` cited
> artefacts present on disk"*. **Both figures in that sentence have moved; the arithmetic
> that reconciles them has not** — the gate still counts the name *Amazon Bedrock* once where
> the census emits two rows for it, which is the whole of the difference between `5` and `6`.
> **The paragraph is left verbatim on purpose**: it is carried word-for-word by
> `RULES-MATRIX.md` §1 so the
> two pages cannot drift apart, that file is not this one's to edit, and correcting one copy
> alone would break the only mechanism keeping them equal. Re-derive both sides —
> `python scripts/submission/check_submission_ready.py` for the gate's figure,
> `evidence/tool-usage/aws-services.json#totals.by_verdict.EXERCISED` for this page's — and
> correct the two copies together. Recorded as owed in
> [`docs/demo/ON-SCREEN-CLAIMS.md`](demo/ON-SCREEN-CLAIMS.md) § *Discrepancies filed, not
> smoothed*.
>
> **Second annotation, 2026-08-16, because one of those two figures moved again and this page
> is why.** Re-run today the gate prints *"`5` AWS service(s) marked as having run …; `34` of
> `34` cited artefacts present on disk"*. The `5` is unchanged and the arithmetic above still
> reconciles it. The `28` became `34` because **Tool 3 gained six citations into
> [`evidence/mcp/`](../evidence/mcp/README.md)** — the day-of-submission MCP capture — and all
> six resolve, which is the whole of the movement. The `2026-08-15` reading above is left
> exactly as it was taken: it was true on its date, and a figure that is silently refreshed
> stops being a measurement.

| service | verdict | files | mechanism (`file:line`) | evidence |
|---|---|---|---|---|
| Bedrock — Claude inference | **EXERCISED** | 355 [src: evidence/tool-usage/aws-services.json#rows.aws_bedrock_runtime.file_count] | `packages/mainline-agentkit/src/mainline_agentkit/transport.py:273` | [`evidence/deploy/aws-live.json`](../evidence/deploy/aws-live.json) — `Converse` `200`, **request id `3c7a283c-9f67-4d98-aa8f-26490d54d32d`**, `stop_reason end_turn`; also [`evidence/aws/probe/raw-haiku-converse.json`](../evidence/aws/probe/raw-haiku-converse.json), [`evidence/aws/agent/live-run.json`](../evidence/aws/agent/live-run.json) |
| Bedrock — embeddings | **EXERCISED** | 76 [src: evidence/tool-usage/aws-services.json#rows.aws_bedrock_embeddings.file_count] | `verticals/mainline/packages/mainline-recall-agent/src/mainline_recall_agent/providers/bedrock_titan.py:55` | [`evidence/deploy/aws-live.json`](../evidence/deploy/aws-live.json) — Titan v2 `InvokeModel` `200`, **request id `b4d826e9-03ba-4368-9687-f00cc28a98ef`**, `1024`-d; and [`evidence/aws/probe/raw-titan-invoke.json`](../evidence/aws/probe/raw-titan-invoke.json) — **request id `6dcdcdf0-38d3-453f-a476-fa69b2d87863`**; also [`evidence/aws/embeddings/manifest.json`](../evidence/aws/embeddings/manifest.json), [`evidence/aws/ann/ann-proof.json`](../evidence/aws/ann/ann-proof.json) |
| CloudWatch | **EXERCISED** (metrics read; alarms now applied, never fired) | 125 [src: evidence/tool-usage/aws-services.json#rows.aws_cloudwatch.file_count] | `scripts/aws/cloudwatch_evidence.py:299` | [`evidence/aws/cloudwatch/bedrock-metrics.json`](../evidence/aws/cloudwatch/bedrock-metrics.json), [`evidence/aws/cloudwatch/reconciliation.json`](../evidence/aws/cloudwatch/reconciliation.json); the log group, four alarms and dashboard are among the 24 created in [`evidence/deploy/APPLIED.md`](../evidence/deploy/APPLIED.md), and **no artefact records any alarm transitioning to `ALARM`** |
| **Bedrock — `cohere.embed-v4`** | **REFUSED in-region** | *(counted in the embeddings row)* | `scripts/aws/_common.py::CROSS_REGION_PREFIXES` | [`evidence/aws/probe/raw-cohere-refusal.json`](../evidence/aws/probe/raw-cohere-refusal.json) — `400`, **request id `a826eb16-e813-45aa-932e-4696e9979087`**; [`evidence/aws/bench/residency-finding.json`](../evidence/aws/bench/residency-finding.json) |
| **Bedrock Rerank** | **NOT-AVAILABLE** | 25 [src: evidence/tool-usage/aws-services.json#rows.aws_bedrock_rerank.file_count] | `verticals/mainline/packages/mainline-recall-agent/src/mainline_recall_agent/rerank/listwise.py:77` | absent in `ap-southeast-2`; no dependency taken. [`evidence/aws/probe/model-availability.json`](../evidence/aws/probe/model-availability.json) is the live census it is absent from |
| S3 + Object Lock | DESIGNED | 139 [src: evidence/tool-usage/aws-services.json#rows.aws_s3_object_lock.file_count] | `infra/modules/evidence-store/main.tf:100` | none — not applied; the live check is one of the seven that did not run. *One S3 bucket does exist — the Terraform **state** bucket in [`APPLIED.md`](../evidence/deploy/APPLIED.md), no Object Lock, no checkpoint — and it promotes nothing* |
| KMS | DESIGNED | 48 [src: evidence/tool-usage/aws-services.json#rows.aws_kms.file_count] | `packages/trappoint-ledger/src/trappoint_ledger/signer.py:63` | none — unit-tested against an injected client only |
| CloudTrail | DESIGNED | 40 [src: evidence/tool-usage/aws-services.json#rows.aws_cloudtrail.file_count] | `infra/envs/evidence/main.tf:114` | none — no trail exists in the account |
| Lambda | **EXERCISED** | 45 [src: evidence/tool-usage/aws-services.json#rows.aws_lambda.file_count] | `infra/modules/demo-api/main.tf:432` (the authorisation decision); the function opens at `:326` | [`evidence/deploy/APPLIED.md`](../evidence/deploy/APPLIED.md) — *"terraform apply 24 created, 0 changed, 0 destroyed"*, `37` resources in state; [`evidence/deploy/live-health.json`](../evidence/deploy/live-health.json) — `ok true`, `deploy_chain 271/271`; [`evidence/deploy/live-gate-run.json`](../evidence/deploy/live-gate-run.json) — four beats, verdict `PROVEN`; [`evidence/deploy/judge-walk.json`](../evidence/deploy/judge-walk.json). The plan it was applied from is [`terraform-plan-furl.txt`](../evidence/deploy/terraform-plan-furl.txt)`:843`, `Plan: 24 to add, 0 to change, 0 to destroy.` — `11` in `module.api[0]`, `13` in `module.guard[0]` |
| CloudFront + OAC | DESIGNED | 103 [src: evidence/tool-usage/aws-services.json#rows.aws_cloudfront.file_count] | `infra/modules/demo-site/main.tf:299` | none — **excluded from the plan**, and not by choice: `403 AccessDenied`, account not verified for new CloudFront resources. See below |
| IAM | **EXERCISED** (the allow half only) | 40 [src: evidence/tool-usage/aws-services.json#rows.aws_iam.file_count] | `infra/modules/demo-api/main.tf:260` (the role that was created and assumed); the deny-first document is `infra/modules/evidence-store/main.tf:145` | [`evidence/deploy/APPLIED.md`](../evidence/deploy/APPLIED.md) — the role, its inline `dsn_access` policy and the managed attachment are 3 of the 24 created (plan lines `195`, `237`, `270`); the role was assumed and its one grant used, per `live-health.json`. **The deny-first evidence-store policies are still unapplied** and Rego asserts them against plan fixtures, offline |
| SSM Parameter Store | **EXERCISED** | 28 [src: evidence/tool-usage/aws-services.json#rows.aws_ssm_parameter_store.file_count] | `infra/modules/demo-api/main.tf:280` (the grant); the signed call is `…/demo-api/src/mainline_demo_api/db.py:214` | [`evidence/deploy/APPLIED.md`](../evidence/deploy/APPLIED.md) with the parameter ABSENT — `ok=false reason="dsn_unset"`, `ParameterNotFound` — and [`evidence/deploy/live-health.json`](../evidence/deploy/live-health.json) with it present — `ok true`. The plan sets `MAINLINE_DSN_PARAM` and no `MAINLINE_DSN` (`terraform-plan-furl.txt:325`), so there is no other path to that answer |
| EventBridge | DESIGNED | 34 [src: evidence/tool-usage/aws-services.json#rows.aws_eventbridge.file_count] | `verticals/mainline/apps/steward/schedules.yaml:14` | none — and there is no `aws_cloudwatch_event_*` resource anywhere under `infra/` |

**Four `mechanism` cells have moved in this module, and every old value is named rather
than erased.** On 2026-08-14 the Lambda row cited `infra/modules/demo-api/main.tf:310`,
which reads `test = "StringEquals"` — a condition operator inside an unrelated policy
statement — and the SSM row cited `:192`, which reads `LOG_LEVEL = var.log_level`. On
2026-08-15 the census's own anchors were found at `:333`
(`handler = "mainline_demo_api.app.handler"`) and `:215` (a bare `#`), and the generator
refused to write. All four are the same drift, in the same 978-line module, and all four are
exactly the *"citation onto a closing brace"* failure this page describes below: they
resolved perfectly and told a reader nothing. The tree is authoritative and this column is
derived, so the column moved — `authorization_type = var.url_authorization_type` is at
`:432`, `resource "aws_lambda_function" "this"` opens at `:326`,
`resource "aws_iam_role" "this"` at `:260`, and `actions = ["ssm:GetParameter"]` at `:280`.
**Nothing under `infra/` or `evidence/` was edited to make this table true.**

Each row's full `verdict_basis` — the sentence that has to be re-derivable from a committed
artefact — is at `evidence/tool-usage/aws-services.json#rows.<key>.verdict_basis`, and for
the six EXERCISED rows those sentences quote their figures in the form
`artefact#/json/pointer = number`, which `scripts/aws/verify_evidence.py` resolves and
compares on every CI run. A number here that has drifted from the JSON behind it is a red
build, not a footnote.

## Amazon Bedrock — inference · **EXERCISED**

**Live in the account, and now measured rather than enumerated.** Region `ap-southeast-2`
(Sydney) carries `8` `au.*` Claude inference profiles plus `amazon.titan-embed-text-v2:0`
and `cohere.embed-v4:0`; that census is re-taken from a live `ListInferenceProfiles` in
[`evidence/aws/probe/model-availability.json`](../evidence/aws/probe/model-availability.json).

**How.** `bedrock-runtime` `Converse` / `InvokeModel` with the Anthropic native body. The
`modelId` is an `au.*` inference-profile identifier **resolved at start-up** rather than
hard-coded, so a Claude generation shipping without an `au.*` profile fails loudly instead
of silently reaching another region.
`packages/mainline-agentkit/src/mainline_agentkit/transport.py:273` refuses any identifier
lacking the `au.` prefix as a residency violation, and
`tests/unit/recall_providers/test_no_hardcoded_model_ids.py` fails the build on a
hard-coded model id anywhere. No sampling parameter is sent on any generation (A6); the
probe records `sampling_parameters_sent: []` on the wire.

One model generation across the whole fleet, differentiated by **effort** rather than by
model — low for triage and extraction, high for adjudication, xhigh for listwise reranking.
One model id means one profile ARN in the endpoint policy means one `403` path instead of
two.

**Verdict: EXERCISED — and read the three limits with it.** A live `Converse` against
`au.anthropic.claude-haiku-4-5-20251001-v1:0` returned `HTTP 200` with an AWS request id
and `stopReason end_turn`
[src: evidence/aws/probe/raw-haiku-converse.json#payload.response.metadata.http_status],
and the **shipped orchestrator** then ran seven live legs through the same profile
[src: evidence/aws/agent/live-run.json#payload.leg_count], each recorded as a cassette that
replays to a byte-identical decision hash
[`evidence/aws/agent/determinism.json`](../evidence/aws/agent/determinism.json). AWS's own
metric series corroborates the calls from outside this repository. The limits:

* the live legs ran on **Haiku 4.5**, while the shipping request builders target the pinned
  Opus generation — four builder fields are refused on the wire by Haiku, projected at the
  wire field by field and never written back into a builder;
* **no live leg refused** [src: evidence/aws/agent/live-run.json#payload.refusal_behaviour.live_refusals_observed],
  so "a refusal degrades the run and the gate still holds" was exercised against a
  *constructed* refusing transport, not against a model that said no;
* everything else in the agent suite still replays a **recorded cassette**, and a green
  cassette test proves the code handles that recorded exchange and nothing about a live
  model's behaviour today.

**A second, independent transcript, taken on a different day by a different program.**
[`evidence/deploy/aws-live.json`](../evidence/deploy/aws-live.json) is a four-call probe
written by `scripts/deploy/aws_live_probe.py` on `2026-08-11T01:11:53Z`, profile
`mainline-dev`, region `ap-southeast-2`, `boto3` `1.43.66`. It exists because a single
artefact is a single point of failure for a claim, and because this one records the whole
round trip — the identity, the model list, and both invocations — in one file a reader can
open in ten seconds:

| call | what came back |
|---|---|
| `sts:GetCallerIdentity` | HTTP `200`, request id `04018eca-8928-459e-92a6-edffe73e34df`, principal `arn:aws:iam::<account>:user/mainline-dev` — the account field is stripped structurally, and its SHA-256 is recorded instead so two artefacts can be shown to name one account without publishing it |
| `bedrock:ListFoundationModels` | HTTP `200`, `64` models offered in region; both requested ids present, Titan as `ON_DEMAND` and Haiku 4.5 as `INFERENCE_PROFILE` |
| `bedrock-runtime:InvokeModel` on `amazon.titan-embed-text-v2:0` | HTTP `200`, request id `b4d826e9-03ba-4368-9687-f00cc28a98ef`, `1024`-dimension embedding, L2 norm `1.0`, `13` input-text tokens, `286.5` ms |
| `bedrock-runtime:Converse` on `au.anthropic.claude-haiku-4-5-20251001-v1:0` | HTTP `200`, request id `3c7a283c-9f67-4d98-aa8f-26490d54d32d`, reply `"MAINLINE gate online"`, `stopReason end_turn`, usage `{inputTokens 16, outputTokens 8, totalTokens 24}` |

`calls_attempted` `4`, `calls_failed` `[]`, `total_seconds` `1.75`. The token counts are
Bedrock's own, taken from the response rather than counted here. The full embedding vector
is deliberately **not** stored — dimension, first eight components, L2 norm and the
SHA-256 of the whole array identify it again at three orders of magnitude less bulk.

Re-derive it, with a credential of your own:

```bash
AWS_PROFILE=mainline-dev python scripts/deploy/aws_live_probe.py
```

**This file supersedes an earlier finding in this repository, and the correction is worth
reading.** `docs/STATE-OF-THE-BUILD.md` §3.3 recorded, on 2026-08-10, that every Bedrock
call returned `ValidationException: Operation not allowed` and that
`get-foundation-model-availability` answered `authorizationStatus: NOT_AUTHORIZED`. That
was true when it was measured. Model access was enabled in the account on 2026-08-11 and
the calls above are what the same code now returns. The old finding is quoted rather than
deleted, in §3.3 and here, because what changed was an account setting and not a line of
code — and a reader whose own account is in the earlier state needs to be able to
recognise it.

See [`docs/HONESTY.md`](HONESTY.md) § SYNTHETIC.

## Amazon Bedrock — embeddings · **EXERCISED**

`amazon.titan-embed-text-v2:0` at
`verticals/mainline/packages/mainline-recall-agent/src/mainline_recall_agent/providers/bedrock_titan.py:55`,
with `cohere.embed-english-v3` as the in-region alternative. Embeddings are written into the
C-SPANN sidecar tables described above, and **every embedding row stores its `embed_model`
and `index_gen`** — `verticals/mainline/db/migrations/0031_clause_embedding.sql` carries
`CONSTRAINT embed_model_stated` and `CONSTRAINT index_gen_stated` — because a vector whose
model is unknown cannot honestly be compared with anything.

**Verdict: EXERCISED.**
2060 [src: evidence/aws/embeddings/manifest.json#payload.totals.vectors] vectors of width
1024 [src: evidence/aws/embeddings/manifest.json#payload.dimensions] were produced by Titan
v2 in `ap-southeast-2` for
177345 [src: evidence/aws/embeddings/manifest.json#payload.totals.input_tokens] input
tokens, enumerated one per row with a text digest, a vector digest and a token count; and
1080 [src: evidence/aws/ann/ann-proof.json#payload.vectors.rows_searched] of them were
searched through CockroachDB's `ce_ann` index with both prefix columns bound. **The corpus
is SYNTHETIC** and the vector blobs live under the gitignored `out/`, so the manifest's
per-vector SHA-256 is the checkable part.

### Two single-call round trips, each naming an AWS request id

A corpus is a strong claim and a hard one to spot-check. So the same model is also recorded
one call at a time, twice, by two different programs on two different days — and each
transcript carries the request id AWS returned:

| artefact | call | AWS request id | what it recorded |
|---|---|---|---|
| [`evidence/aws/probe/raw-titan-invoke.json`](../evidence/aws/probe/raw-titan-invoke.json) | `bedrock-runtime:InvokeModel`, 2026-08-10 | `6dcdcdf0-38d3-453f-a476-fa69b2d87863` | HTTP `200`, `1024`-d, L2 norm `1.00000006`, `36` input-text tokens, full response body committed |
| [`evidence/deploy/aws-live.json`](../evidence/deploy/aws-live.json) | `bedrock-runtime:InvokeModel`, 2026-08-11 | `b4d826e9-03ba-4368-9687-f00cc28a98ef` | HTTP `200`, `1024` dimensions against an expected `1024`, L2 norm `1.0`, `13` input-text tokens |

**Two L2 norms, and the difference is not a discrepancy — read it before quoting either.**
The probe records `1.00000006`; the live-probe records `1.0`. They are **different calls on
different texts**, and the two programs round differently: `raw-titan-invoke.json` publishes
the norm to eight places because it is asserting that Titan's `normalize: true` returns a
vector that is unit-length *to within float error*, which is a claim `1.0` would hide. A
figure copied from one file into a sentence about the other would be a fabrication with a
true-looking value, which is the hardest kind to catch. Each number above is quoted only
against the file that produced it.

The manifest above is the corpus; these two are the round trips.

Tier-2 verification in `VERIFY.md` — clone, `just up`, `just migrate`, `just conform` —
still needs **no model call and no cloud account at all**, because the committed fixtures
are unchanged. The refusal still reproduces on a stranger's laptop.

## Amazon Bedrock — `cohere.embed-v4` · **REFUSED in-region, and that refusal is a residency finding**

This section exists for the same reason the Bedrock Rerank section below it does: **a
services document that silently drops what you tried and could not have is a document
nobody can audit.** The difference is that Rerank was simply absent, while `cohere.embed-v4`
is present, is better on paper, and was **not adopted** — which is a decision, and decisions
are the part a reader cannot re-derive from a file listing.

**What was measured.** A `bedrock-runtime:InvokeModel` against the bare model id
`cohere.embed-v4:0` in `ap-southeast-2` was **refused**, HTTP `400`, request id
`a826eb16-e813-45aa-932e-4696e9979087`
[`evidence/aws/probe/raw-cohere-refusal.json`](../evidence/aws/probe/raw-cohere-refusal.json).
AWS's own words, recorded verbatim and hashed, with `redaction_altered_message: false`:

> `Invocation of model ID cohere.embed-v4:0 with on-demand throughput isn't supported.`
> `Retry your request with the ID or ARN of an inference profile that contains this model.`

**So which inference profile contains it?** Exactly one, of `29` visible in the region:
`global.cohere.embed-v4:0`
[`evidence/aws/bench/residency-finding.json`](../evidence/aws/bench/residency-finding.json).
AWS describes it, again verbatim, as *"Routes requests to Embed v4 globally across all
supported AWS Regions."* Its member list includes a **regionless** ARN
(`arn:aws:bedrock:::foundation-model/cohere.embed-v4:0`), so the region that serves a given
request is chosen by AWS at call time and **is not observable to the caller**.

**Why that is disqualifying here, stated precisely.** MAINLINE embeds Australian safety
narratives and commits to doing it in `ap-southeast-2` —
`providers/bedrock_titan.py::REQUIRED_REGION` and `providers/resolve.py::REQUIRED_REGION`,
both constants, both test-enforced. The harm is **not** that the data certainly leaves the
region. It is that *"these narratives were embedded in Australia"* becomes **unverifiable**
the moment that identifier is used, and an unverifiable residency claim is worse than no
claim, because it reads like one. This project's own guard agrees without being asked:
`scripts/aws/_common.py::CROSS_REGION_PREFIXES` lists `apac`, `eu`, `global`, `us`, and
`residency-finding.json`'s `our_own_residency_guard` block shows the guard **admitting**
`cohere.embed-v4:0` and **refusing** `global.cohere.embed-v4:0`.

**The in-region answer, named rather than implied: `cohere.embed-english-v3`.** It is
`ON_DEMAND` in `ap-southeast-2`, needs no profile, and is the only Cohere embedder this
account can reach without breaking residency. **It carries its own measured limit and it is
published too:** Bedrock refuses any single text over `2048` characters for it —
`Malformed input request: #/texts/0: expected maxLength: 2048, actual: 4680` — which `96` of
the `1071` corpus documents exceed. Titan v2 accepted the same `4680`-character probe at
`782` tokens.

**What was decided.** Titan v2 was kept, **no provider code changed**, and the question ADR
`0002` left open is recorded as answered: not *"which model scores higher"* but *"residency
or that model"*. The cross-region arm was invoked **once, deliberately, on a synthetic probe
string**, to measure what refusing it costs — `1536` dimensions, L2 norm `1.00000006` — and
the flag that permitted that one call is recorded in the artefact rather than left implicit.

## Amazon Bedrock Rerank — **NOT-AVAILABLE**

**Not offered in `ap-southeast-2`, and no dependency was taken on it.**
[`evidence/aws/probe/model-availability.json`](../evidence/aws/probe/model-availability.json)
is the live control-plane census of what this region *does* offer, and Rerank is not in it;
`docs/HONESTY.md` records the absence in prose. It is listed here rather than omitted because
a services list that silently drops what you checked for and could not have is a list nobody
can audit.

**The absence cost nothing, and that is the part worth reading.** Listwise reranking is done
by the Claude profile at high effort —
`verticals/mainline/packages/mainline-recall-agent/src/mainline_recall_agent/rerank/listwise.py:77`
is the class that does it — and on the retrieval side CockroachDB's own
`vector_search_rerank_multiplier` session variable (observed at `50`, with
`vector_search_beam_size` at `32`) governs ANN candidate expansion. The design assumed
Rerank's absence **before** it was checked, and the check agreed.

*This row's citation points at the substitute rather than at the sentence announcing the
gap, and that was a deliberate second choice.* It first pointed into `docs/HONESTY.md` by
line number; that file is under active edit and the line moved within the hour, which the
new anchor guard caught. **A line number into a prose document somebody else is rewriting is
a citation with a short half-life.** The reranker moves only when the mechanism moves.

## S3 + Object Lock — the evidence store · **DESIGNED**

`infra/modules/evidence-store/main.tf` — `aws_s3_bucket:74`, `versioning:89`,
`object_lock_configuration:100`, `public_access_block:113`, `bucket_policy:335`.

**How.** Checkpoints of the tamper-evident ledger are appended to a versioned bucket in
**COMPLIANCE** mode, which even the root account cannot shorten. `object_lock_enabled` is
set **at bucket creation** because it cannot be added afterwards — the module treats that as
a one-shot and refuses a plan that would create a second bucket. The writer identity is
denied `s3:DeleteObjectVersion` and denied `PutObjectRetention` with an unconstrained
retention date, so the identity that appends checkpoints cannot shorten or remove them.

`infra/policy/custody/object_lock.rego` and `infra/policy/custody/kms_custody.rego` assert
each of those denials against `plan_compliant.json` and a family of deliberately broken
plans under `infra/policy/custody/fixtures/`, each named for the control it removes:
`ol1_no_object_lock`, `ol2_versioning_suspended`, `ol3_governance_one_year`,
`ol4_public_policy_allowed`, `ol5_sse_kms`, `kms1_destruction_ungated`,
`kms2_rotation_enabled`, `kms3_seven_day_window`, `kms4_symmetric_key`,
`iam1_writer_can_delete`, `iam2_unconstrained_retention`, `gt18_two_buckets`,
`destroy1_key_deleted`, `plan1_unresolved_policy`. A policy suite that has only ever seen a
passing plan asserts nothing.

**Verdict: DESIGNED, and this is the sharpest limitation in this document.** No bucket has
been applied. From `docs/HONESTY.md`: *the AWS evidence store is described, not exercised
under load* — the bundle's archive section carries object-lock modes and retention dates,
and **the check that would compare them against live object versions is one of the seven
cryptographic checks that did not run**
[src: qa/test-state.json#external_checks.custody_bundle_verification.counts.not_checked].
The offline custody verification exits `2`
[src: qa/test-state.json#external_checks.custody_bundle_verification.exit_code] precisely
so that nobody reads its nine passes
[src: qa/test-state.json#external_checks.custody_bundle_verification.counts.passed] as a
verified ledger.

## AWS KMS — the checkpoint signing key · **DESIGNED**

`packages/trappoint-ledger/src/trappoint_ledger/signer.py:63` and the key resources at
`infra/modules/evidence-store/main.tf:477` / `:501`.

**How, and why each choice is a choice.** `ECC_NIST_P256`, `SIGN_VERIFY`,
`ECDSA_SHA_256`, and **`MessageType = RAW`** — KMS hashes the message itself. Passing our
note text under `DIGEST` would have KMS hash it a *second* time and produce a valid
signature over the wrong thing, which is precisely the failure KMS exists to prevent, so
the constant names itself loudly at
`packages/trappoint-ledger/src/trappoint_ledger/signer.py:69`. DER signatures are stored
**exactly as KMS returns them**, with no re-encoding to fixed-width `r‖s`, because the offline verifier
calls Go's `ecdsa.VerifyASN1` and the two must agree byte for byte. Rotation is **off** —
a rotated signing key silently invalidates historical verification — and key deletion is
gated, with `boto3` imported inside the adapter rather than at module scope so the whole
package stays importable, and testable, on a machine with no AWS at all.

The threat model is explicit at
`packages/trappoint-ledger/src/trappoint_ledger/signer.py:196`: a T1 adversary holding
arbitrary SQL has no path to `kms:Sign`.

**Verdict: DESIGNED.** Unit-tested against an injected client; the live signature check is
another of the seven that did not run.

## AWS CloudTrail — custody of the custodian · **DESIGNED**

`infra/envs/evidence/main.tf:114`, multi-region, with `enable_log_file_validation`.

**How.** Log-file validation makes AWS produce **its own signed digest chain** over the
same events — weaker than ours, because AWS holds the key, and valuable for exactly that
reason: **it is a chain we could not have forged.** Two advanced event selectors: management
events, so `kms:ScheduleKeyDeletion`, `PutKeyPolicy`, `PutBucketPolicy` and
`PutObjectLockConfiguration` become visible to the custody patrol within one checkpoint
cadence instead of at the next audit; and data events on the checkpoint bucket, which are
expensive on a busy bucket and trivial on this one at `1440` objects a day.

**Verdict: DESIGNED.** No trail exists in the account. Note the interaction with the
`ccloud` limitation above: the *control-plane* half of "custody of the custodian" has no
input source on the Basic tier regardless of CloudTrail, because the Cloud audit-log
endpoints `404`.

## Amazon CloudWatch — **EXERCISED**, read-only, and the distinction is the point

`scripts/aws/cloudwatch_evidence.py:299` is a `before-call` guard that raises for any
operation outside a six-item read-only allow-list **before the request is signed**. That is
what makes the verdict phrase *"metrics read, nothing provisioned"* mechanical rather than a
promise.

**How, and why it is the most valuable AWS evidence in this repository.** `AWS/Bedrock`
publishes `Invocations`, `InputTokenCount`, `OutputTokenCount`, `InvocationThrottles` and
error counts per `ModelId`, for free, with **nothing provisioned**. Reading them is an
attestation **written by AWS** that this repository's code ran — the one witness in the tree
we did not author. Each `Sum` is taken at `Period` `300` *and* `3600` and required to agree,
because a `Sum` is resolution-invariant and a disagreement would mean a clipped bucket and
two untrustworthy numbers.

110 [src: evidence/aws/cloudwatch/bedrock-metrics.json#payload.api_call_summary.GetMetricStatistics]
read-only `GetMetricStatistics` calls produced the series. **The per-model totals are
deliberately not retyped into this page.** They are sums over a window whose end moves with
every run of the reader, so a figure copied here would go stale silently; instead
`evidence/tool-usage/aws-services.json#rows.aws_cloudwatch.verdict_basis` quotes them in the
`artefact#/json/pointer = number` form that `scripts/aws/verify_evidence.py` resolves and
compares on every CI run, and the artefact itself is one click away. A number that cannot be
kept true is better left where it is generated.

**And the deltas are published rather than smoothed.**
[`evidence/aws/cloudwatch/reconciliation.json`](../evidence/aws/cloudwatch/reconciliation.json)
subtracts this repository's own token ledgers from AWS's counters and **names every
non-zero difference**: probes made before the fleet's first artefact existed, SDK-internal
retries that are separate HTTP requests AWS served and counted, and an unattributed residual
from iterations run while these programs were being written — calls **no artefact in this
repository records, so no artefact in this repository may claim them.**

**What was DESIGNED here, and what changed on 2026-08-14.** The log group with finite
retention (`infra/modules/demo-api/main.tf:239`), the four metric alarms (`:581` errors,
`:615` throttles, `:648` duration p99, `:757` concurrency) and the dashboard (`:841`) were
**written and unapplied**. *This paragraph cited `main.tf:391` for all six until 2026-08-14;
that line is a comment inside the function resource about an `ELFCLASS` error, and it named
none of them.* They are **applied now** — they are among the `24` resources in
[`evidence/deploy/APPLIED.md`](../evidence/deploy/APPLIED.md), together with the cost
guard's three further alarms and its own log group. **Two things are unchanged and both
matter.** First, existing is not firing: **no artefact in this repository records any alarm
transitioning to `ALARM`**, so what is evidenced is the resource, never the threshold.
Second, and this is the sentence the CloudWatch verdict rests on: **no log group, alarm,
dashboard, metric filter or IAM role was created by any program in this evidence fleet** —
`bedrock-metrics.json`'s `prohibitions` block asserts each of those false about its own run
and reads the account state back to check. The reader that took the metrics still provisions
nothing; the orchestrator's `terraform apply` is a different program with a different
authorisation.

## AWS Lambda, IAM, SSM Parameter Store — the demo stack · **EXERCISED**

**And Amazon CloudFront + OAC, which is in this section because it is part of the same
design — DESIGNED, and on this account it cannot be applied at all.**

**This heading read *"the demo stack · all DESIGNED"* until 2026-08-15.** Three of the four
moved when `terraform apply` ran on 2026-08-14 — `24` created, `0` changed, `0` destroyed,
[`evidence/deploy/APPLIED.md`](../evidence/deploy/APPLIED.md) — and the fourth did not move
and cannot, for the reason below. The diagram is now a description of something a judge can
open rather than of something planned.

**The shape below is not the shape this document described until 2026-08-12, and the
correction is the most important paragraph in Part 2.** This section used to state that the
Function URL's `authorization_type` was **`AWS_IAM`, never `NONE`**, invoked only by
CloudFront over an OAC signature. **The committed plan does the opposite**, for a measured
reason, and a submission document whose security posture disagrees with its own committed
Terraform is worse than one that says nothing. **It is now the applied posture too, not only
the planned one.**

```
judge's browser ──/v1/*──► Lambda Function URL (authorization_type = NONE, public)
                                    │ pgwire, TLS, same region
                                    ▼
             CockroachDB Cloud Basic · mainline-dev · Singapore
```

**Why there is no CloudFront in that diagram.** A real `terraform apply` against this
account returned, verbatim:

```
Error: creating CloudFront Distribution: StatusCode: 403,
RequestID: 3e63e30d-8c5b-441b-a01b-b70085eba504, AccessDenied:
Your account must be verified before you can add new CloudFront resources.
```

It reproduces from a bare `aws cloudfront create-distribution` with **no Terraform
involved**, and the calling identity holds `AdministratorAccess` — so it is an **account-level
verification hold that only AWS Support can lift**, not a permissions bug and not something
this repository can fix. It is recorded at `infra/modules/demo-api/main.tf:22` and in
`docs/deploy/RUNBOOK.md` §1, which is written as though *the hold never clears*, because a
runbook that assumes a support queue will answer in time is not a runbook.

**The consequence propagates, and both rows say so.** With no distribution there is no
principal to grant `lambda:InvokeFunctionUrl` to. An `AWS_IAM` Function URL with nothing
authorised to sign for it is not a hardened demo — **it is a demo nobody, including the
judges, can reach.** So `var.url_authorization_type` defaults to `NONE`
(`infra/modules/demo-api/variables.tf:103`, the `default = "NONE"` line itself),
`infra/modules/demo-api/main.tf:432` passes it to the URL, the plan carries
`authorization_type = "NONE"` (`evidence/deploy/terraform-plan-furl.txt:351`),
`enable_cloudfront` is `false`, and **no `aws_cloudfront_*` resource appears among the plan's
`24` additions**.

*Three citations in that sentence moved on 2026-08-14, and each moved because the artefact
said so.* The default was cited as `main.tf:310`, which today reads `test = "StringEquals"`.
The plan's `authorization_type` was cited as `furl.txt:329`, which today reads
`+ "MAINLINE_RATE_GLOBAL_RPS" = "10"`; the attribute is at `furl.txt:351`. And the additions
were given as `11`: `evidence/deploy/terraform-plan-furl.txt:843` reads
`Plan: 24 to add, 0 to change, 0 to destroy.` — **`11` in `module.api[0]` and `13` in
`module.guard[0]`.** The `11` was true before the cost guard was wired in at
`infra/envs/demo/main.tf:631`; it is the API module's own count and it is still `11`.

**A public URL is a public gateway to a database, and this module does not pretend
otherwise.** What actually bounds it is written down rather than assumed — and **the first
item on that list used to be false, so it is corrected here rather than dropped.** This
paragraph said `reserved_concurrent_executions` *"is a hard cap that **stops** a bill rather
than reporting one"*. **The committed plan sets `reserved_concurrent_executions = -1`**
(`evidence/deploy/terraform-plan-furl.txt:296`) — no reservation at all — because this
account's Lambda concurrency ceiling is `10` and AWS refuses every positive reservation
against it. The same correction is already recorded in the census's own
`rows.aws_lambda.verdict_basis`, dated 2026-08-13, and this page had not absorbed it. So what
bounds the bill is: **nothing named in this module.** The handler's write surface is one
transaction that ends in `ROLLBACK`, and the CockroachDB Basic cluster carries its own
`spend_limit` — but **neither of those two is under attack in a flood**, where the target is
the static tree. The concurrency alarm **reports and does not stop.** The only thing bounding spend today
is the account's measured concurrency ceiling of `10`, which is `Adjustable: true` and which
nobody in this repository chose; `docs/deploy/COST-BOUND.md` carries the arithmetic. That is
a **much smaller** claim than *"invocable by one distribution and nothing else"*, and it is
the true one for this account.

* **Lambda** — one `python3.13` `arm64` function
  (`infra/modules/demo-api/main.tf:326`, `256 MB`, `14 s`) behind the Function URL at
  `:425`, whose authorisation is decided at `:432`. *This bullet read `main.tf:238`, `512 MB`
  and `15 s`; `:238` is a blank line, and the committed plan gives `memory_size = 256`
  (`furl.txt:290`) and `timeout = 14` (`furl.txt:315`). The plan artefact is authoritative
  for what would be created and this prose is derived from it.* It runs in `ap-southeast-1`
  beside the cluster because the same call from `ap-southeast-2` pays roughly `90 ms` each
  way and the gate screen makes six of them — about `1.1 s` of pure geography on the one page
  judges look at.
* **CloudFront + Origin Access Control** — one distribution
  (`infra/modules/demo-site/main.tf:299`) with two OACs (`:273`, `:286`) is **written and
  excluded**. As designed it would front both the private S3 origin holding the static
  console and the Lambda Function URL, so a judge saw one origin and the bucket was never
  public; OAC (not the legacy OAI) signing both origins is what would let the Function URL
  keep `AWS_IAM`. None of that is deployed and, on this account, none of it *can* be.
* **IAM** — **two halves, and only one of them is in the account.** The half that ran is the
  Lambda execution role (`infra/modules/demo-api/main.tf:260`), created by the apply,
  assumed by the function, whose entire non-managed grant is `ssm:GetParameter`
  (`:280`) on **one** parameter ARN (`:285`, `resources = [local.dsn_parameter_arn]`) plus a
  conditioned `kms:Decrypt`. The half that did not is **the interesting one — what is
  denied**: `infra/modules/evidence-store/main.tf:145` is the policy document that denies the
  checkpoint writer `s3:DeleteObjectVersion` and denies `PutObjectRetention` without a
  bounded retention date, and **that module has never been applied**; Rego asserts each
  denial against plan fixtures, offline, and nowhere else.
  *Cited as `:192` and `:197` until 2026-08-14; `:192` reads `LOG_LEVEL = var.log_level`.*
* **SSM Parameter Store** — the CockroachDB Cloud DSN is a SecureString parameter, **not** a
  Lambda environment variable, so the connection string never appears in the function
  configuration that anyone holding `lambda:GetFunction` can read. Terraform is given the
  parameter's **name**, never its value: a Terraform-managed secret is a plaintext secret in
  the state file, and the state bucket has a wider read audience than the parameter does.
  The call is hand-rolled SigV4 over one HTTPS request
  (`verticals/mainline/apps/demo-api/src/mainline_demo_api/db.py:214`) and the result is
  cached for the life of the container, so a warm request makes no SSM call at all.

**Verdict: three EXERCISED, one DESIGNED-and-unapplyable, and the paragraph this replaces is
worth keeping in view.** It read *"Verdict on all four: DESIGNED, and deliberately still
DESIGNED … An authorised plan is not an apply."* That was correct on the day it was written
and it is how these rows are supposed to behave — a verdict does not move on an intention.
The apply then happened, on 2026-08-14, against the plan committed at
[`evidence/deploy/terraform-plan-furl.txt`](../evidence/deploy/terraform-plan-furl.txt)`:843`
— `Plan: 24 to add, 0 to change, 0 to destroy.`, being `11` in `module.api[0]` and `13` in
`module.guard[0]` — and
[`evidence/deploy/APPLIED.md`](../evidence/deploy/APPLIED.md) records `24 created, 0 changed,
0 destroyed` with `37` resources in state. **Lambda, IAM and SSM Parameter Store moved on
that transcript and on the live readings beside it; CloudFront did not and will not, because
this account is refused new distributions.** Two limits ride along with the promotion:
the IAM verdict covers the role's allow and **not** the deny-first evidence-store policies,
and `docs/submission/SUBMISSION.json` remains the **single write point** for the submission's
`demo_url` — a URL existing and a URL being *submitted* are different facts and this page
settles only the first.

## Amazon EventBridge — DESIGNED, and weaker than the others

`verticals/mainline/apps/steward/schedules.yaml:14` describes scheduled invocations keyed
by `(schedule_id, occurrence_ts)`, where `occurrence_ts` is EventBridge's
`<aws.scheduler.scheduled-time>` — the same value on every retry of one occurrence, which
is what makes a run idempotent. The schedule is external by necessity: CockroachDB's
`CREATE SCHEDULE` exists only for backups and changefeeds, so no part of this system may
assume in-database cron.

**Stated plainly: there is no `aws_cloudwatch_event_*` or scheduler resource anywhere under
`infra/`.** Today the schedule lives in that YAML file and a container entrypoint. This row
is DESIGNED in the weakest sense of the word, and it is listed because leaving it out of a
services document while the runbooks name it would be the wrong kind of tidy.

---

# Part 3 · Where this actually runs, and what that costs

| layer | where |
|---|---|
| Database | CockroachDB v26.2.5 Basic, **`aws-ap-southeast-1` — Singapore** |
| Demo stack (designed) | Lambda Function URL, **`ap-southeast-1` — Singapore**. CloudFront is written and **excluded**: `403 AccessDenied`, account not verified for new distributions |
| Inference | Amazon Bedrock, **`ap-southeast-2` — Sydney** |

Sydney is Advanced-tier only for CockroachDB Cloud, so it is absent from the Basic region
list. **Any claim of end-to-end Australian data residency is false for this deployment**,
and the split is stated here, in `VERIFY.md`, and in the README, and is nowhere rounded
off.

**Cost.** The cluster carries a configured `spend_limit` of `2500` (`US$25.00`/month) — a
ceiling, not a spend — against free-tier allowances of `100M` request units and `10 GiB`,
all three quoted from the captured transcript above. The cheapest deployment satisfying
*"functional demo URL, free and unrestricted for judges"* is a static console build with
committed replay fixtures, which needs no server, no credential
and no egress, at **`US$0`/month**, against roughly `US$5–8`/month for the cheapest
always-on container.

---

# Part 4 · What is NOT claimed

Collected here so a judge does not have to hunt for it. Every line is also in
[`docs/HONESTY.md`](HONESTY.md).

* **Bedrock Rerank is unavailable in `ap-southeast-2`.** No dependency was taken.
* **`ccloud` `0.6.12` cannot authenticate headlessly.** Agent paths use the Cloud REST API.
* **Cloud audit-log endpoints `404` on Basic.** "Custody of the custodian" has no
  control-plane input source on this tier.
* **The S3 object-lock check did not run** — one of the
  7 [src: qa/test-state.json#external_checks.custody_bundle_verification.counts.not_checked]
  cryptographic checks registered, named, and reported as *not checked* rather than passed.
* **No live Bedrock *refusal* was observed.** Seven live agent legs all returned
  `end_turn`, so the "a refusal degrades the run and the gate still holds" path was
  exercised against a **constructed** refusing transport. The claim about refusal handling
  rests on a fabricated refusal, and that is stated in the artefact that makes it.
* **No live run on the shipping model generation.** The live legs are Haiku 4.5; the request
  builders target the pinned Opus generation, and the four fields Haiku rejects on the wire
  are listed field by field rather than smoothed over.
* **Neither cassette loader hashes the response.** Both live stores ship an `INDEX.json`
  carrying `response_sha256` and a test that recomputes it, because changing a replay path's
  behaviour belongs in its own reviewed commit rather than in an evidence run.
* **Nothing has ever run against CockroachDB Cloud in CI.** The nightly truth check is
  designed, not scheduled.
* ~~**No live MCP session against the managed endpoint is captured.**~~ **Retired
  2026-08-11, and the census caught up on 2026-08-12**: `evidence/deploy/judge-run.json`
  captures one, `15` of `16` pack questions PASS over the managed endpoint against the live
  Basic cluster, and `crdb_managed_mcp` now reads EXERCISED. Three things stay true and are
  *not* retired: the run's own verdict is `DIVERGED — KNOWN GAP` for a real reachability
  gap (`N01`); the MCP credential is **not publishable to anonymous judges**, so this is not
  the judge access path; and the *suites* still skip with a reason rather than pass empty
  when no key is present. See Tool 3.
* **`cohere.embed-v4` cannot be used in-region on this account.** The bare model id is
  refused on-demand (`400`, request id `a826eb16-e813-45aa-932e-4696e9979087`) and its only
  inference profile is the cross-region `global.cohere.embed-v4:0`. The in-region answer is
  `cohere.embed-english-v3`, which itself refuses any text over `2048` characters — `96` of
  `1071` corpus documents. Titan v2 was kept; **no provider code changed**. This is a
  limitation published, not routed around.
* **This account cannot create a CloudFront distribution.** `403 AccessDenied`, *"Your
  account must be verified before you can add new CloudFront resources"*, reproduced without
  Terraform by an identity holding `AdministratorAccess`. CloudFront is therefore excluded
  from the committed plan, and the demo's Function URL is **public** (`authorization_type =
  NONE`) rather than `AWS_IAM` — a weaker posture than the one originally designed, stated
  here rather than left to be discovered in the plan file.
* ~~**Nothing has been applied, including what is authorised.**~~ **Retired 2026-08-15, and
  the sentence it replaces is kept because it is the rule.** It read: *"A `terraform apply`
  is planned, reviewed and authorised as this document is written. Lambda, IAM, SSM Parameter
  Store and CloudFront remain DESIGNED, because authorised is not applied and the verdict
  column would be worthless if intent could move it."* The apply ran on 2026-08-14
  ([`evidence/deploy/APPLIED.md`](../evidence/deploy/APPLIED.md), `24 created`), so three of
  those four moved on a transcript rather than on the intention. **CloudFront did not move
  and cannot**, and the IAM promotion covers the execution role's allow and **not** the
  deny-first evidence-store policies, which remain unapplied.
* **The conformance suite has never been demonstrated.** Against a bare node its cases
  *error* rather than skip; `just migrate && just conform` is the invocation that would run
  them. This is the single largest gap between what the repository contains and what it has
  shown.
* **Half of the AWS surface is still not deployed, and it is the custody half.** Three of the
  six EXERCISED rows are *API calls against services AWS already operates* — model inference
  and read-only metrics — and three are the applied demo stack. **Five rows still require a
  `terraform apply` that has not happened**: no evidence bucket, no Object Lock, no KMS
  signing key, no trail, no distribution, no schedule rule. The evidence store is the one a
  reader should care about most, because the custody claim rests on it, and it is the one
  that is not there. Separately: **`docs/submission/SUBMISSION.json` is the single write
  point for the submission's `demo_url`**, and a URL existing is not a URL submitted — take
  that value from that file, never from this page.
* **The AWS corpus is SYNTHETIC.** Every document embedded and searched was generated by
  `trappoint_recall.corpora.synthetic`, because every source record in this domain is a real
  death and a repository is a copy. The Bedrock calls, the vectors, the CockroachDB writes
  and the index traversal are real; the subject matter is not.
* **The ANN evidence database's parent table is a stub.** `mainline_ann_evidence` copies
  `0031_clause_embedding.sql` verbatim but its `clause_version` parent carries none of the
  production triggers, so **nothing there demonstrates the gate**. The production table is
  exercised separately, with exactly one row.

---

# Part 5 · Re-deriving every number here

```bash
# the two censuses this document cites for every file count.
# --check answers TWO questions and fails on either:
#   1. are the committed JSON files byte-identical to a fresh census of this tree?
#   2. does every `N [src: evidence/tool-usage/...]` number ON THIS PAGE equal the
#      value it cites? Regenerating the artefacts does not update the prose, and a
#      fresh census under a stale sentence is the false negative that matters.
#   3. does every row's anchor still land on the line's declared subject? It refuses
#      with exit 2 BEFORE 1 and 2 are computed, which is what it did on 2026-08-14 on
#      two drifted anchors. Both were re-pointed in the GENERATOR on 2026-08-15 and it
#      exits 0. Counts move whenever anybody adds a file, so run it; do not assume it.
python scripts/submission/capture_tool_evidence.py            # write
python scripts/submission/capture_tool_evidence.py --check    # non-zero if any of the three is stale
python scripts/aws/verify_evidence.py --list                  # the same anchor rule, as [CEN-ANCHORS]

# the node every "Measured on the pinned local node" block ran against
just up     # cockroachdb/cockroach:v26.2.5, single node, insecure
#   DSN: postgresql://root@localhost:26257/defaultdb?sslmode=disable

# the refusal this document calls the product
python scripts/proof/gate_refusal.py --dsn postgresql://root@localhost:26257/defaultdb?sslmode=disable

# the test and check census the honesty numbers come from
python scripts/qa/report_test_state.py

# every AWS number in Part 2, checked without our credentials
python scripts/aws/verify_evidence.py             # 39 invariants, stdlib only, no network
python scripts/aws/verify_evidence.py --list      # the invariant table
python scripts/aws/verify_evidence.py --self-test # plant one defect per family; each must fire

# the four-call live probe behind evidence/deploy/aws-live.json — needs YOUR credential
AWS_PROFILE=mainline-dev python scripts/deploy/aws_live_probe.py
```

Reference format: `[src: path#json.path.to.value]`, resolved against
`evidence/tool-usage/*.json`, `evidence/aws/**/*.json`, `evidence/gate-refusal/*.json` and
`qa/test-state.json`. A number in this document with no reference beside it is a defect;
report it.

**The `evidence/aws/**` references are the newest, and they are the ones a sceptic should
pull on first.** Everything they point at was written by a program holding credentials you
do not have. `scripts/aws/verify_evidence.py` is the answer to that: it checks the
artefacts against each other and against this census, needs no account, and refuses to pass
if any EXERCISED verdict cites a file that is not there.

Related reading: [`VERIFY.md`](../VERIFY.md) — three ways to check the claim without
trusting us. [`docs/HONESTY.md`](HONESTY.md) — everything this build gets wrong, counted.
[`evidence/tool-usage/README.md`](../evidence/tool-usage/README.md) — how the censuses are
built and why they carry no timestamp.
