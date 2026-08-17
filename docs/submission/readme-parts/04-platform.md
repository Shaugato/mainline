## What it is built on

Three words carry the tables below. **EXERCISED** — it ran, and a committed file in this
repository records the result. **DESIGNED** — the code or configuration is finished and on disk,
and nothing we recorded has run it end to end. **NOT-AVAILABLE** — we checked on this platform,
it was absent, and nothing here was built on it.

**Four CockroachDB tools**, in the order the judging criterion names them, each row saying what
the agent *did* with the tool. A **vector index** finds the most similar records without
comparing every one. Our published tool census files the database itself as a fourth tool and the
vector index as an engine feature [src: evidence/tool-usage/crdb-features.json#totals.by_kind];
this table follows the criterion's list instead.

| # | tool, in the criterion's order | verdict | what the agent actually did with it |
|---|---|---|---|
| 1 | Distributed vector index — C-SPANN `VECTOR INDEX` | **EXERCISED** | The agent's retrieval step asks for the most similar earlier clauses, with the index named in the statement. It then reads the query plan back and asserts the index was chosen. Without that naming the plan is a declared `FULL SCAN` — every row read — and it returns plausible results, so a silent degradation would look like working retrieval. |
| 2 | MCP Server — CockroachDB Cloud's managed Model Context Protocol endpoint | **EXERCISED** | An MCP client dialled CockroachDB's own managed endpoint and drove a sixteen-question judge pack over read verbs only. No write verb was ever sent, and the capture program enforces that at the transport rather than promising it. |
| 3 | `ccloud` CLI — the CockroachDB Cloud command-line tool | **EXERCISED** | Ran `ccloud auth whoami`, then `ccloud cluster list -o json`, and parsed the structured output instead of screen-scraping it. |
| 4 | Agent Skills | **DESIGNED** | **Nothing this repository records has run them.** Two authored skills and one staged upstream contribution are on disk, each shipping a script that fails when its guarantee does not hold. No run of either script is captured under `evidence/`, so they are shipped and not evidenced. This row is not promoted to make the table look even. |

**Twelve AWS services: six EXERCISED, five DESIGNED, one NOT-AVAILABLE**
[src: evidence/tool-usage/aws-services.json#totals.by_verdict]. What moved: Amazon Bedrock
inference, Bedrock embeddings and CloudWatch metric reads — calls against services AWS already
runs. Then Lambda, AWS IAM (identity and access management) and Systems Manager Parameter Store,
on a `terraform apply` that created real resources, recorded in
[`evidence/deploy/APPLIED.md`](evidence/deploy/APPLIED.md). What did not move: **S3 with Object
Lock, KMS (the key management service), CloudTrail, CloudFront and EventBridge** are still
DESIGNED — no MAINLINE evidence bucket, no signing key, no trail, no distribution, no schedule
rule. Bedrock Rerank is the NOT-AVAILABLE row: AWS does not offer it where our inference runs.

**CloudFront is not DESIGNED by choice; it is blocked.** A real apply attempt returned
`AccessDenied: Your account must be verified before you can add new CloudFront resources.`,
kept verbatim with its `RequestID` in [`docs/deploy/RUNBOOK.md`](docs/deploy/RUNBOOK.md)
Appendix A. Only AWS Support can lift that hold, so the demo's origin is the Lambda Function URL
itself. **The IAM promotion is narrower than its row title**: what ran is the execution role's
single allow, and the deny-first evidence-store policies remain unapplied.

**Bedrock executes in this repository and NOT in the demo request path.** Inference runs in
Sydney, `ap-southeast-2`, while the database is in Singapore, `aws-ap-southeast-1`, because
`ap-southeast-2` is Advanced-tier only on CockroachDB Cloud. There is no end-to-end Australian
residency, and the cross-region hop is unmeasured under load.

Every row's file and line is in [`docs/TOOL-USAGE.md`](docs/TOOL-USAGE.md).
`python scripts/aws/verify_evidence.py` re-checks the censuses with the standard library alone
— no credential, no network — and fails if any EXERCISED row's cited artefact is missing.
