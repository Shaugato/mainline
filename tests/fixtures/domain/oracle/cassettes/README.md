<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# Path B cassettes

Committed recordings for `mainline-delta-oracle`, worker W5. Every file is keyed
`sha256(profile_id || prompt_version || jcs(call_input))` and every one carries
`"provenance": "synthetic"`: AWS credentials were not valid on the build machine
as of 2026-08, so **none of these responses has been near Bedrock**. That field is
what tells a synthetic recording from a live one, and nothing else does.

Regenerate with `mainline_delta_oracle.cassettes.record_scenarios(root)`. The
committed files are compared against a fresh generation by
`tests/unit/domain/resolution/test_oracle_cassettes.py`, so a stale fixture is a
failing build rather than a discovery.

| scenario | expects | keys |
|---|---|---|

| `contradicts_high` | weaken at band high — the money path | `47e576dc26f3aeb6…` |
| `entails_high` | strengthen — a numeric claim supported by a quoted number | `48a93c90023a363d…` |
| `neutral_high` | restate accepted above theta | `5a9581ff50054228…` |
| `neutral_low` | below theta — resolves to weaken when the paths disagree | `047f3b397f6e274a…` |
| `model_abstains` | abstained — the honest case | `a1e1e0465a9b64f2…` |
| `quote_not_verbatim` | abstained — fabricated evidence, rejected by the verifier | `c2be63e90d5fde0e…` |
| `unsupported_numeric_claim` | abstained — 'entails' with a numeric disagreement and no number quoted | `0573542f09651527…` |
| `schema_violation` | abstained — invalid twice, then dead-lettered | `7a5e7391f7d4c630…`<br>`ee6a4f1ad60fd84e…` |
| `truncated` | abstained — a truncated structured output is fatal by decision A5 | `2d1d7c39221e7048…` |
| `guardrail_intervention` | abstained — Guardrails blocked the response | `3838c8917ec4b0ae…` |
| `model_refusal` | abstained — a refusal on a cyanide corpus is plausible and is silence | `678aff5224bae4eb…` |

`schema_violation` carries two keys because the one permitted retry is a second
call whose input includes the validator's own complaint about the first. Both
have to be on disk or the dead-letter path cannot be replayed at all.
