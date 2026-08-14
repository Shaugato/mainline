<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# First light — the demo answering PROVEN on a public URL

`https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws`

Measured 2026-08-15 by driving the real Function URL over the public internet. Nothing here
is a local run, a stub, or a recording: the transcripts beside this file are the responses
that URL returned.

## `GET /v1/health`

    ok                    True
    database              mainline_demo
    cluster_version       CockroachDB CCL v26.2.5
    deploy_chain_applied  271   of 271 files
    schema_fingerprint    ec9b1ce70a8df066e5763056c5ad9376800ef5df9362f7d0502b1dc7e745
    applied_by            scripts/deploy/cloud_chain.py
    warm response         0.0149 s

`migrations_applied` reads **0** and that is TRUE, not broken: two appliers write two
ledgers, and this database was built by `cloud_chain.py`, which writes
`trappoint.deploy_chain` (271) rather than `trappoint.schema_migration` (0). The endpoint
reports both and names which one it is quoting.

## `POST /v1/demo/gate-run` — VERDICT **PROVEN**

| beat | what it does | SQLSTATE | matched |
|---|---|---|---|
| `read` | the permit, and the obligation still open on it | `00000` | yes |
| `merge` | MERGE with one open obligation and no signed disposition | **`23514`** `gate_closed_when_issued` | yes |
| `projection_drift_attack` | force the projected counter to zero and merge anyway | **`P0001`** `mainline.fn_permit_merge_gate` | yes |
| `admit` | sign one disposition against the obligation, then merge | `00000` | yes |

The two refusals are the product. The gate declines a merge the paperwork does not support,
and then declines it a second way when the counter it reads is falsified underneath it —
because the gate re-derives rather than trusting. The admission proves the refusal was a
decision and not an inability: the same merge, with the obligation properly disposed of, is
admitted.

## What it took to get here, recorded because it is the interesting part

The console was deployed in REPLAY. It shipped compiled with `VITE_MAINLINE_BUNDLE_URL` and
an EMPTY `VITE_MAINLINE_API_BASE`, so every byte a reader saw was a recorded evidence bundle
rather than the kernel the page was sitting on — and `demo_gate_run` was not among the
resources the console declares, so the headline beat had no control at all. The packer check
that existed to catch exactly this keyed on the variable NAME and never on its VALUE, and
Vite always emits an empty `VITE_MAINLINE_API_BASE`, so the guard was unreachable code that
had never once executed. `--console-transport` is now a required declaration compared
against what the artefact measurably does.

**The founder found that by opening the URL.** No test in this repository did, because every
one of them read source and none read the built artefact.

Then five privilege gaps, discovered one HTTP request at a time until the scan was widened
to every schema:

    mainline.defeater_option and 7 others   SELECT
    schema trappoint                        USAGE  (an EXECUTE grant already there was unusable without it)
    trappoint.deploy_chain + 2              SELECT
    mainline_meas.agent_action, .silence_ledger, mainline_ops.outbox   SELECT

**There is not one GRANT statement in the 271 migrations.** Every privilege `mainline_api`
holds was granted by hand, so every table added since — `defeater_option` among them — was
silently missed, and the role that the public endpoint runs as could not read the vocabulary
a signature has to pin. That is the same shape as every other defect this project has found:
the thing that was set up and the thing that ships drifted apart, and nothing compared them.
It is recorded here as an open finding rather than closed quietly.

`mainline_api` now holds CONNECT 1 · USAGE 37 · SELECT 66 · UPDATE 3 · INSERT 8 · EXECUTE 29.
The write set is untouched. For comparison the admin role on this cluster holds `ALL` on 417
objects, and the Function URL is `authorization_type = NONE` by the founder's explicit
choice — which is why the endpoint runs as the narrow role and not that one.
