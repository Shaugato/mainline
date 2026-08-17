## How we got here, and what we found out about CockroachDB

We did not begin with a database idea. We began by reading how permits are issued. The UK Health and Safety
Executive's guide HSG250 lists thirteen essential elements of a permit form. Six permit products say what
they block on — *"locks permit progress until all mandatory checks are completed"*
[src: docs/demo/research/r3-operator.md §1–§2]. Every one of those checks is about the present, and none of
the thirteen is *why*. The information is not missing — somebody wrote it down — it is unreachable at the
moment of the decision, and a rule keeps its authority only while somebody remembers where it came from.

The obvious answer is to show the reason beside the Approve button. We did not build that. An agent writes over
whatever surface it can reach, and it does not stop being an agent when it uses `psql`, the database's own command
line. A panel can therefore be dismissed and a retrieval can go unread [src: docs/submission/JUDGING-AXES.md §1].
The only version nobody can dismiss is one where the refusal is a property of the write itself, so this memory
lives in constraints and triggers, not in application code [src: spec/invariants/I02-projected-refusal.md]. That
made the database the product, and it is why the findings below cost us real time.

### Five things we measured on CockroachDB v26.2.5, offered as field notes

Each row names its kind: **defect** — we believe the platform is wrong; **limit** — documented behaviour we hit;
**ours** — we misread the platform. **None of this has been reported to Cockroach Labs**; the one thing staged
upstream is an unrelated skill contribution, not yet filed [src: docs/upstream/proposal-issue.md].

| finding | kind | what we measured | written down at |
|---|---|---|---|
| `has_function_privilege()` cannot answer `false` | defect | On a throwaway database with `EXECUTE` revoked from everyone, calling the procedure was refused — `42501 … does not have EXECUTE privilege on procedure merge_permit`. The function still answered `true`: for that login, for `root`, for `admin`, for `public`. `has_table_privilege` passed the identical control and tracked behaviour exactly. A permission check built on the first one can never fail. | [`docs/regression/GUARD.md`](docs/regression/GUARD.md) §*Two things this guard found on its first run* — local node, 2026-08-15 |
| two catalogues spell one routine two ways | ours | `SHOW GRANTS` names a routine with its full argument list; `information_schema.routines` gives the bare name. Comparing them without normalising the spelling produced false positives. That was our bug. Nothing ships between the two surfaces to normalise them, so our regression guard keeps a planted failure alive to prove the trap is still exercised. | [`docs/regression/GUARD.md`](docs/regression/GUARD.md), the planted-failure cases P2 and P3 |
| the vector index is not chosen at demo scale | limit | At 5,200 rows, unless the index is named in the statement, the database scans and then filters. A cost-based planner legitimately prefers a scan on a small table — correct behaviour that broke our assumption. We now name the index and assert the plan rather than hoping. | [`docs/adr/0002-g1-platform-ground-truth.md`](docs/adr/0002-g1-platform-ground-truth.md) GT-06 / GT-06b; [`evidence/aws/ann/explain-unhinted.txt`](evidence/aws/ann/explain-unhinted.txt) |
| the managed MCP endpoint truncates rather than raising | limit | Responses are capped at 10,240 bytes, and a cut answer is byte-for-byte indistinguishable from a complete one — nothing on the response says it was cut. A wrong count looks exactly like a right one. We shaped our own views to 80 % of the cap so growth breaks in CI instead of in front of a reader. | [`docs/TOOL-USAGE.md`](docs/TOOL-USAGE.md) §*Feedback on the CockroachDB AI tools*; [`packages/mainline-mcp/src/mainline_mcp/limits.py`](packages/mainline-mcp/src/mainline_mcp/limits.py) line 60 |
| `ccloud` 0.6.12 has no headless login | limit | `ccloud auth` offers only `login` / `logout` / `whoami`, `login` opens a browser, and `CC_API_KEY` in the environment is ignored. An agent cannot drive the command-line tool from a cold start; our headless paths use the Cloud REST API with the same key instead. | [`evidence/ccloud/README.md`](evidence/ccloud/README.md) |

**A sixth candidate did not survive checking.** We expected to report `crdb_internal` and `system` as
restricted on the Basic tier. They are refused `42501` by default on v26.2.5 everywhere — local single node
included — a version default, not a tier constraint [src: evidence/tool-usage/crdb-features.json].

**What we would keep unchanged.** `CHECK` constraints and PL/pgSQL triggers under `SERIALIZABLE` — concurrent
writes behave as if run one after another — carry this product. The refusal names the constraint that raised
it, precise enough to put on screen: `23514 gate_closed_when_issued` [src: docs/deploy/cloud-database.md].

Two more we measured and left out — a 20,000 schema-object ceiling our own scratch databases reached quietly, and an untyped `convert_from()` — are
written up where they happened [src: docs/submission/EXTRA-CREDIT-CLAIMS.md; verticals/mainline/db/seeds/demo/demo_world.sql:844].
