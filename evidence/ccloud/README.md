<!--
SPDX-FileCopyrightText: 2026 MAINLINE
SPDX-License-Identifier: CC-BY-4.0
-->

# ccloud CLI — captured evidence

Real output from the `ccloud` CLI against the project's live CockroachDB Cloud cluster. Captured 2026-08-10. Nothing here is reconstructed or hand-written.

- `cluster-list.txt` — `ccloud auth whoami` followed by `ccloud cluster list -o json`, verbatim (ANSI spinner frames stripped, nothing else altered).

## What it establishes

```
logged in to "Not Applicable" (org-3bkz4) as Shaugato-AWS Paroi
```

```json
{
  "name": "mainline-dev",
  "cockroach_version": "v26.2.5",
  "plan": "SERVERLESS",
  "cloud_provider": "AWS",
  "regions": [{ "name": "ap-southeast-1", "primary": true }],
  "config": { "serverless": {
      "routing_id": "mainline-dev-31219",
      "spend_limit": 2500,
      "usage_limits": { "request_unit_limit": "100000000", "storage_mib_limit": "10240" }
  }}
}
```

The `-o json` flag is the point: this is **parsed, not screen-scraped**. `spend_limit: 2500` is the $25.00 monthly cap configured at cluster creation; `request_unit_limit` and `storage_mib_limit` are the free-tier allowances.

## The honest limitation (see `docs/leads/agents-mcp.md` F7)

`ccloud` **0.6.12** is the latest published build (0.7.0 / 0.8.0 / 0.9.0 / 1.0.0 all return 404 from `binaries.cockroachdb.com`). It has **no non-interactive service-account authentication**: `ccloud auth` exposes only `login` / `logout` / `whoami`, `login` is browser-based, and `CC_API_KEY` in the environment is ignored. The session it caches is scoped to the interactive Windows logon and is not readable from a non-interactive shell.

**Therefore an agent cannot drive `ccloud` headlessly from a cold start**, and MAINLINE does not claim that it does.

What MAINLINE does claim, and what is demonstrated here and in `evidence/ccloud-api/`:

1. **`ccloud` is used, with `-o json` parsed rather than screen-scraped** — for human-run and replayable-transcript paths. This file is that transcript.
2. **The same service-account credential drives the CockroachDB Cloud REST API for headless paths.** Verified live against `/clusters`, `/clusters/{id}`, `/service-accounts`, `/api-keys`, and `/clusters/{id}/sql-users`.

A further measured limitation: **audit-log endpoints are not available on this tier.** `/auditlogentries`, `/auditlogs`, `/audit-logs` and the cluster-scoped variant all return 404. The custody design's *"custody of the custodian"* mechanism — folding control-plane audit records into the tamper-evident ledger — therefore has no input source on Basic/Serverless and is documented as unavailable rather than shipped as an unbacked claim.
