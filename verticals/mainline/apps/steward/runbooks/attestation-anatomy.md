<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# Anatomy of an `ops_attestation`

For the reader who has been handed one file and one database row and asked whether they
mean anything.

## The two artefacts

| Artefact | Where | What it is |
|---|---|---|
| `<schedule>@<ts>.ops-attestation.json` | `/opt/steward/run`, and S3 Object Lock in the deployed posture | the **canonical** RFC 8785 bytes of the payload. Not pretty-printed; a reformatted copy hashes differently and would look like tampering |
| one row in `mainline_meas.external_attestation` | the cluster | the commitment: `detail_sha256 = SHA-256(0x00 ‖ canon_bytes)` |

The row is small because the table is. The payload is large because a review is. The link
between them is one hash, computed the same way `mainline.ledger_intake.leaf_hash` is
computed — RFC 6962 §2.1 leaf domain separation — so a verifier already written for the
custody ledger recognises the shape.

## The payload, field by field

```
attestation_kind    "ops_attestation"
spec_version        1
disclaimer          an LLM ops report is evidence that a review occurred, not
                    evidence of a condition
run
  schedule_id       from schedules.yaml
  occurrence_ts     EventBridge <aws.scheduler.scheduled-time>, UTC, second resolution
  occurrence_key    <schedule_id>@<occurrence_ts>   ← the idempotency key
  site_code         the ledger partition
  outcome           verified | indeterminate | failed
  outcome_means     what that value means HERE, in words, in the payload
identity
  agent_identity    sha256 over the seven A13 inputs, length-framed
  identity_source   local_fallback | mainline_provenance:… | explicit
  …the seven inputs, in clear, so the digest is recomputable
mcp
  mcp_cluster_id    the cluster the mcp-cluster-id header pinned
  mcp_endpoint      https://cockroachlabs.cloud/mcp
  write_surface     mainline_meas.external_attestation
runtime
  agent_runtime_version   from `claude --version`, observed not declared
  allowed_tools           read out of settings.json, not restated
  prompt_version          the digest of the prompt tree
  narrative_source        session_json | unparsed | missing | absent
  transcript_sha256       over the raw session bytes
skills[]
  commit, path, skill_sha256, file_count, pin_state, upstream_url
findings[]
  statement         the exact SQL, generated from the contract
  result_sha256     sha256 of the RFC 8785 canonical rows
  row_count, response_bytes, completeness, elapsed_ms
  narrative         the model's prose, or null
  narrative_is_not_evidence   true
```

## Reading `outcome` correctly

`outcome` is about **the review**, not about the cluster.

- `verified` — every contracted read answered and the attestation assembled. It is **not**
  a statement that anything is healthy. A run in which every number was terrible and every
  read answered is `verified`.
- `indeterminate` — at least one contracted read did not answer. The remaining findings
  are **not** coverage; something was not looked at.
- `failed` — the run could not be assembled.

`outcome_means` is written into the payload in words precisely because the three column
values invite the wrong reading.

## Reading `pin_state` correctly

Each skill carries `pin_state`:

- `enforced` — the lock recorded an `expected_sha256` and the checkout matched it. A
  mismatch would have refused the run before any read.
- `recorded_only` — the lock pinned the commit and carried no content digest, so the
  digest in this attestation was computed and recorded but not compared.

`recorded_only` exists because the machine that wrote the lock had the upstream commit and
not the upstream bytes, and writing a digest that had not been computed would have been an
invented fact in an evidentiary file. Run `mainline-steward skills verify --record` once
against a real checkout, commit the result, and every pin becomes `enforced`.

## Reading `identity_source` correctly

`agent_identity` is `sha256(agent_name ‖ sql_role ‖ iam_role_arn ‖ prompt_version ‖
model_id ‖ inference_profile_arn ‖ schema_version)` (decision A13), which makes a prompt
edit a *different agent*.

`‖` needs a framing rule, because concatenating variable-length fields is ambiguous. This
package length-frames each field. If the provenance worker's canonical resolver frames
differently, the digests differ — which is why `identity_source` names which
implementation produced it and why all seven inputs are carried in clear beside it. A
reader can always recompute; they never have to guess.

## What the narrative is worth

Exactly as much as prose from a competent reviewer who cannot be cross-examined. It sits
beside a statement and a hash that were produced without it, and
`narrative_is_not_evidence: true` is on every finding because a field that is prose should
say so in a record that will outlive everybody who knew.

If the narrative and the numbers disagree, the numbers are the record. Re-run the
statement.
