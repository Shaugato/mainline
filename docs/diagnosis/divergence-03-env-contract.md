<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Environment-variable contract — divergence census

## Verdict

Twelve environment names are read by the code that is actually inside the Lambda package,
and eight are published by the Terraform that would create it. I enumerated all three
layers and settled the third by **executing a plan and reading its JSON**, not by reading
`.tf` source: `terraform … plan` (11 to add) then `show -json` gives the
`aws_lambda_function` `environment.variables` map verbatim, and it holds exactly eight
keys. Diffing that map against the reader inventory in both directions gives **seven
read-but-unpublished** names (five of which cannot be published from the shipping root at
all) and **three published-but-unread** names.

Of nineteen pairs enumerated: **0 DIVERGENT** — no name is published under a spelling the
code does not read, and no published value is wrong today. **2 HELD** by an executable
mechanism. **17 LATENT** — they agree, or are harmless, because of a default, a trigger,
or a dead field, and in sixteen of the seventeen cases the `held by` column is the word
NOTHING. The single most important measured fact is not a mismatch but a *shape*: under
the plan's exact environment, `scenario.from_env()` returns a **two-family hybrid** — the
permit from the seeded `dec0de00-…` family and the site, clause and event from the
`uuid5` family that `grep` finds zero times in either seed file. It is not the fourth
NO-GO only because a `BEFORE INSERT` trigger overwrites one of the three and nothing reads
the other two. `scenario._selfcheck()` (`scenario.py:130-142`) passes in every one of
those cases, because it compares the module with itself.

Nothing in this repository holds the environment contract. `grep -rn "aws_lambda_function"
--include=*.py` returns **zero hits**: no test, script or check ever reads what Terraform
would publish.

---

## The measured layers

**Layer 1 — every name any Python module reads with a literal.** Across the repo,
**267** distinct names (measured; the brief's figure of 209 predates the concurrent wave),
of which **42** begin `MAINLINE_`. Only the twelve below are load-bearing for the demo
deployment, because the deployed package contains exactly twelve application modules and
nothing else of ours:

```
$ python -c "import zipfile; z=zipfile.ZipFile('out/lambda/mainline-demo-api-arm64.zip'); \
             print([n for n in z.namelist() if n.startswith('mainline_demo_api')])"
['mainline_demo_api/__init__.py', 'mainline_demo_api/app.py', 'mainline_demo_api/credentials.py',
 'mainline_demo_api/db.py', 'mainline_demo_api/envelope.py', 'mainline_demo_api/gate_run.py',
 'mainline_demo_api/health.py', 'mainline_demo_api/reads.py', 'mainline_demo_api/refusal.py',
 'mainline_demo_api/scenario.py', 'mainline_demo_api/static_site.py',
 'mainline_demo_api/transitions.py']
```

Six of the twelve are **computed, not literal** — `scenario._env_uuid` builds
`ENV_PREFIX + name.replace("-","_").upper()` at `scenario.py:186`, and `from_env`
(`scenario.py:205-212`) calls it with `permit_id`, `site_id`, `clause_uuid`, `event_id`
plus two direct `SIGNER_SUB`/`COUNTERSIGNER_SUB` lookups. A plain `grep` for
`MAINLINE_DEMO_SITE_ID` in `scenario.py` finds nothing; the name exists only after string
concatenation. That is the same class of invisibility as the three NO-GO defects.

**Layer 3 — what a deployed Lambda actually receives.** Nothing is deployed today
(`aws lambda get-function-configuration --function-name mainline-demo-api` →
`ResourceNotFoundException: Function not found`), so the plan is the authority.

```
$ terraform -chdir=<scratch copy of infra>/envs/demo init -reconfigure -no-color
Successfully configured the backend "local"!   … Terraform has been successfully initialized!
$ terraform -chdir=… validate -no-color
Success! The configuration is valid.
$ terraform -chdir=… plan -no-color -input=false -var enable_cloudfront=false \
      -var lambda_package_path=D:/CoackroachDBxAWS/mainline/out/lambda/mainline-demo-api-arm64.zip \
      -out=<scratch>/tfplan-furl.binary
Plan: 11 to add, 0 to change, 0 to destroy.
$ terraform -chdir=… show -no-color -json <scratch>/tfplan-furl.binary > <scratch>/tfplan-furl.json
$ python extract_env.py
ADDRESS: module.api[0].aws_lambda_function.this
LOG_LEVEL='INFO'
MAINLINE_DEMO_COUNTERSIGNER_SUB='demo.countersigner'
MAINLINE_DEMO_DATABASE='mainline_demo'
MAINLINE_DEMO_PERMIT_ID='dec0de00-0006-4000-8000-000000000001'
MAINLINE_DEMO_SIGNER_SUB='demo.signer'
MAINLINE_DSN_PARAM='/mainline/demo/cockroach_dsn'
MAINLINE_SCENARIO_PERMIT_ID='dec0de00-0006-4000-8000-000000000001'
MAINLINE_WEB_ROOT='/var/task/web'
COUNT: 8
```

The whole `infra/` tree was copied to a scratch directory **outside the repository** and
run there, with a `backend "local"` override written only into that copy. No file was
added to, removed from or changed in `infra/`; `infra/envs/demo/.terraform` and the
committed `backend.tf` naming S3 were not touched. Account id appears above only as
`022950218246` in Terraform's own output and is masked everywhere in this document.

---

## Inventory

Reader lines are in `verticals/mainline/apps/demo-api/src/mainline_demo_api/`.
Publisher lines are in `infra/modules/demo-api/main.tf` unless stated.
Values are **verbatim from the plan JSON above**.

### Read and published (5)

| # | name | reader (file:line) | publisher (file:line) | value in the plan | status | held by | sev |
|---|---|---|---|---|---|---|---|
| 1 | `MAINLINE_DSN_PARAM` | `db.py:111`, read `db.py:275` | `main.tf:137` | `/mainline/demo/cockroach_dsn` | HELD | `scripts/deploy/deploy.sh:484-493` parses `infra/envs/demo/variables.tf`'s default and refuses a disagreement at preflight | — |
| 2 | `MAINLINE_WEB_ROOT` | `static_site.py:157`, read `:243` | `main.tf:200` ← `variables.tf:471` | `/var/task/web` | HELD | `deploy.sh:565-579` and `:853-855` assert the build manifest's `web_root` equals `/var/task/web`; manifest measured `/var/task/web` and the zip really has `web/index.html` | — |
| 3 | `MAINLINE_DEMO_PERMIT_ID` | `scenario.py:186,205` (computed) | `main.tf:155` ← `variables.tf:275` | `dec0de00-0006-4000-8000-000000000001` | LATENT | **NOTHING** — `variables.tf:277-280` is `can(regex("^[0-9a-f]{8}-…"))`, which accepts every lowercase UUID including the one that produced NO-GO #1 | LATENT |
| 4 | `MAINLINE_DEMO_SIGNER_SUB` | `scenario.py:209` | `main.tf:177` ← `variables.tf:344` | `demo.signer` | LATENT | **NOTHING** — `variables.tf:354` checks only non-empty + trimmed; the `main.tf:367` precondition checks only `signer != countersigner`. Neither reads `demo_world.sql:125` | LATENT |
| 5 | `MAINLINE_DEMO_COUNTERSIGNER_SUB` | `scenario.py:210-212` | `main.tf:178` ← `variables.tf:395` | `demo.countersigner` | LATENT | **NOTHING** — same two shape checks; `demo_world.sql:133` is cited in prose only | LATENT |

### Read but UNPUBLISHED (7)

| # | name | reader (file:line) | publisher | default silently in force | status | held by | sev |
|---|---|---|---|---|---|---|---|
| 6 | `MAINLINE_DSN` | `db.py:107`, read `db.py:270` | **NONE, by design** | unset → SSM path taken | HELD | `variables.tf:792-805` forbids it in `extra_environment`; `db.py:277-281` raises `DsnUnavailable` naming both names | — |
| 7 | `MAINLINE_DEMO_SITE_ID` | `scenario.py:186,206` (computed) | **NONE** (argued, `main.tf:180-187`) | `c333eb17-a6c8-5729-8e73-8d49a7ab3971` — the uuid5 family | LATENT | **NOTHING** in Terraform or Python. The argument is *correct* and is enforced only by SQL: `0102_fn_disposition_project.sql:55` is `BEFORE INSERT` and `:208` does `NEW.site_id := v_site_id`, so `gate_run.py:607`'s value is overwritten before any constraint sees it | LATENT |
| 8 | `MAINLINE_DEMO_CLAUSE_UUID` | `scenario.py:186,207` (computed) | **NONE, no argument stated** | `512b662e-1208-51a4-be59-ecb4f3ca085f` — uuid5 family | LATENT | **NOTHING** — inert only because the field is dead: its sole consumer is `Scenario.as_json()` (`scenario.py:177`), and the demo path emits `ResolvedScenario.as_json()` instead (`gate_run.py:731`) | LOW |
| 9 | `MAINLINE_DEMO_EVENT_ID` | `scenario.py:186,208` (computed) | **NONE, no argument stated** | `bf94c82a-1aac-5cb0-87c9-b371d958f158` — uuid5 family | LATENT | **NOTHING** — same dead-field reason | LOW |
| 10 | `MAINLINE_DEMO_ALLOW_MUTATION` | `transitions.py:315` | **NONE** — prose only at `variables.tf:773`, `infra/modules/demo-api/README.md:634` | unset → `_mutation_allowed()` is `False`, guard armed | LATENT | **NOTHING**, and it is **unsettable from the shipping root** — see F-1 | MEDIUM |
| 11 | `MAINLINE_DEBUG` | `app.py:477` | **NONE** — same two prose lines | unset → no traceback in 500 bodies | LATENT | **NOTHING**; the safe default is the accidental one | LOW |
| 12 | `MAINLINE_MAX_RESPONSE_BYTES` | `static_site.py:160`, read `:274` | **NONE** — same two prose lines | `2097152` (2 MiB) | LATENT | **NOTHING**, and unsettable from the shipping root — the documented cost lever cannot be pulled by configuration | MEDIUM |

Lambda-runtime-injected names — `AWS_ACCESS_KEY_ID` (`db.py:170`),
`AWS_SECRET_ACCESS_KEY` (`:171`), `AWS_SESSION_TOKEN` (`:172`), `AWS_REGION` /
`AWS_DEFAULT_REGION` (`:283`) — are correctly absent from the map and are refused if a
caller tries to set them (`variables.tf:807-816`). **HELD.**

### Published but UNREAD (3)

| # | name | publisher (file:line) | reader | status | held by | sev |
|---|---|---|---|---|---|---|
| 13 | `MAINLINE_SCENARIO_PERMIT_ID` | `main.tf:154` | **NONE** — `grep -rn "environ.*MAINLINE_SCENARIO_PERMIT_ID" --include=*.py` → 0 hits | LATENT | Declared inert on purpose and recorded at `README.md:640`; the same value is published under the read name at `main.tf:155` | LOW |
| 14 | `MAINLINE_DEMO_DATABASE` | `main.tf:146` | **NONE** in Python | LATENT | **NOTHING** — `main.tf:139-142` claims "a disagreement between the two is a finding", and no code computes that finding: `health.py` reports `current_database()` and never reads this name. See F-4 for the three-layer name collision | LOW |
| 15 | `LOG_LEVEL` | `main.tf:192` | **NONE** in Python | LATENT | Real filtering is `logging_config.application_log_level` (`main.tf:325`) from the same variable, so the two cannot drift | LOW |

### Contract-level pairs (4)

| # | pair | definition A | definition B | status | held by | sev |
|---|---|---|---|---|---|---|
| 16 | module env keys ↔ `extra_environment` deny-list | plan JSON: 8 keys | `variables.tf:793-803`: 9 entries | **HELD** | Executed: `published - denied == []`; `denied - published == ['MAINLINE_DSN']` (deliberate). The `merge()` shadowing hole `variables.tf:780-787` warns about is genuinely closed today | — |
| 17 | `extra_environment` ↔ the shipping root | `variables.tf:770-817` | `infra/envs/demo/` — declared nowhere, passed nowhere | LATENT | **NOTHING** — see F-1 | MEDIUM |
| 18 | `scenario_permit_id` ↔ the shipping root | `variables.tf:245-281` | `infra/envs/demo/` — declared nowhere, passed nowhere | LATENT | **NOTHING** — see F-2 | MEDIUM |
| 19 | module `output "web_root"` ↔ root outputs | `infra/modules/demo-api/outputs.tf:119` | `infra/envs/demo/outputs.tf` — 17 outputs, not this one | LATENT | **NOTHING** — see F-5 | LOW |

---

## Findings

### F-1 The documented escape hatch for every optional switch does not exist in the environment that ships — severity: MEDIUM

- **Divergence:** `infra/modules/demo-api/variables.tf:770-774` declares `extra_environment`
  as *the* way to set "the demo's optional switches — `MAINLINE_DEMO_ALLOW_MUTATION`,
  `MAINLINE_DEBUG`, the other `MAINLINE_DEMO_*` scenario overrides — without giving each of
  them a variable here", and `infra/modules/demo-api/README.md:634` repeats it in the
  environment table. · `infra/envs/demo/main.tf:280-388` is the entire `module "api"` block
  and passes no `extra_environment`; `infra/envs/demo/variables.tf` declares no such
  variable.
- **Command:**
  `grep -rn "extra_environment\|scenario_permit_id\|web_root\|demo_database\|log_level" infra/envs/demo/*.tf`
- **Output:** *(empty — zero matching lines in any of the root's seven files)*
- **What a user or judge sees:** nothing, today — the unset defaults happen to be the safe
  ones (`_mutation_allowed() is False`, no traceback, 2 MiB ceiling). What an **operator**
  sees is that following the module's own documentation is impossible: five of the seven
  read-but-unpublished names (rows 8, 9, 10, 11, 12) cannot be reached from
  `infra/envs/demo` without editing a `.tf` file. In particular the cost lever
  `MAINLINE_MAX_RESPONSE_BYTES` — which `static_site.py:167-169` calls "a real lever" worth
  "roughly a 3.6-fold reduction in the flood's multiplier" — cannot be pulled by
  configuration on a public, unauthenticated Function URL whose worst case is
  USD 33,250/30d.
- **What would have caught it:** NOTHING DOES. There is no check that a module input which
  the module's documentation calls load-bearing is wired at the root that ships.

### F-2 `scenario_permit_id` is not settable from the shipping root — severity: MEDIUM

- **Divergence:** `infra/modules/demo-api/variables.tf:245-281` declares it and
  `infra/modules/demo-api/main.tf:155` publishes it as `MAINLINE_DEMO_PERMIT_ID` ·
  `infra/envs/demo/main.tf:280-388` never passes it and `infra/envs/demo/variables.tf`
  never declares it, so the only way to change the demo's permit is to edit the module's
  `default`.
- **Command:** `terraform -chdir=<scratch>/infra/envs/demo plan -no-color -input=false -var enable_cloudfront=false -var lambda_package_path=… -var scenario_permit_id=dec0de00-0006-4000-8000-000000000001`
- **Output:**
  ```
  Error: Value for undeclared variable

  A variable named "scenario_permit_id" was assigned on the command line, but
  the root module does not declare a variable of that name. To use this value,
  add a "variable" block to the configuration.
  ```
- **What a user or judge sees:** a judge who seeds their own copy hits the
  `423 demo_subject_unidentified` refusal, whose remedy text (`transitions.py:395`) says
  *"Set `MAINLINE_DEMO_PERMIT_ID` to the permit this deployment actually seeded"*, and the
  shipping Terraform root offers no way to do that. `scenario.py:16-21` makes the same
  promise — "Every identifier is also overridable from the environment … without a code
  change" — and for this deployment it is false.
- **What would have caught it:** NOTHING DOES. The value is right today because the module
  `default` at `variables.tf:275` was corrected; the only thing keeping it right is
  `variables.tf:277-280`, a regex that accepts every lowercase UUID — including
  `077a6fdd-2167-559c-b2ff-8e3c8352504d`, the exact value that was NO-GO #1.

### F-3 The deployed scenario is a two-family hybrid: one identifier from the seed, three from the family nothing seeds — severity: LATENT (would be CRITICAL if any of the three were read)

- **Divergence:** `infra/modules/demo-api/main.tf:135-201` publishes `MAINLINE_DEMO_PERMIT_ID`
  and no other identifier · `scenario.py:205-208` reads four, and falls back to
  `demo_uuid(...)` for the three that are absent.
- **Command:** the plan's exact eight variables placed into `os.environ`, then
  `scenario.from_env()` — `python scratchpad/deployed_env.py`
- **Output:**
  ```
  scenario.from_env() under the PLANNED Lambda environment:
  {
    "permit_id":   "dec0de00-0006-4000-8000-000000000001",   ← seed family
    "site_id":     "c333eb17-a6c8-5729-8e73-8d49a7ab3971",   ← uuid5 family, unseeded
    "clause_uuid": "512b662e-1208-51a4-be59-ecb4f3ca085f",   ← uuid5 family, unseeded
    "event_id":    "bf94c82a-1aac-5cb0-87c9-b371d958f158",   ← uuid5 family, unseeded
    "signer_sub":  "demo.signer",
    "countersigner_sub": "demo.countersigner",
    "merged_commit": "4fbbd37106cf5e02b03a49ce2ba5c4aa4fbbd37106cf5e02b03a49ce2ba5c4aa"
  }
  static_site.max_response_bytes() = 2097152 (DEFAULT_MAX_RESPONSE_BYTES = 2097152 )
  static_site.web_root()          = \var\task\web
  transitions._mutation_allowed() = False
  MAINLINE_DEBUG present          = False
  ```
- **Confirmed against three independently chained-and-seeded local worlds** (read-only; the
  three unpublished fallbacks are absent from every one of them, the published values are
  present in every one of them, and the projector's timing is read from the live catalog
  rather than from a comment):
  ```
  $ python scratchpad/dbcheck.py        # postgresql://root@localhost:26257/<db>?sslmode=disable
  created/confirmed d_w3_env_contract
  ===== w_w1_demo =====   (identical output for w_w3_demotruth and w3_demo_api_123396ff6486)
  triggers on mainline.disposition:
      ('disposition_close',        'AFTER',  'INSERT', 'fn_disposition_close')
      ('disposition_project',      'BEFORE', 'INSERT', 'fn_disposition_project')
      ('disposition_retract_only', 'BEFORE', '',       'fn_disposition_retract_only')
  constraints on mainline.disposition mentioning site_id:
      (none)
    permit dec0de00-0006 (PUBLISHED MAINLINE_DEMO_PERMIT_ID):            1
    permit 077a6fdd (scenario.py fallback):                              0
    site c333eb17 (unpublished MAINLINE_DEMO_SITE_ID fallback):          0
    clause 512b662e (unpublished MAINLINE_DEMO_CLAUSE_UUID fallback):    0
    event bf94c82a (unpublished MAINLINE_DEMO_EVENT_ID fallback):        0
    signing_credential signer_sub = demo.signer (PUBLISHED):             1
    signing_credential signer_sub = demo.countersigner (PUBLISHED):      1
  ```
  Two things follow that reading could not settle. `disposition_project` really is
  `BEFORE INSERT` in the catalog, so `NEW.site_id := v_site_id` runs before constraint
  evaluation; and **no constraint on `mainline.disposition` mentions `site_id` at all**, so
  the overwrite is the only thing that value ever meets. The three unpublished identifiers
  name **no row in any seeded world**.
- **What a user or judge sees:** nothing today, and the reason is worth stating exactly
  because it is luck rather than design in two of the three cases:
  * `site_id` **does** reach the write path — `gate_run.py:607` passes
    `resolved.scenario.site_id` into `_DISPOSITION_SQL` — and is neutralised in SQL:
    `verticals/mainline/db/migrations/0102_fn_disposition_project.sql:55` states the
    projector is `BEFORE INSERT`, and `:208` is `NEW.site_id := v_site_id;`, taking the
    site from `blocking_check` instead. The client value is overwritten before any
    constraint evaluates it. The module's claim at `main.tf:180-187` is therefore correct
    — but it is held by a trigger, not by anything that would fail if the trigger changed.
  * `clause_uuid` and `event_id` reach **nothing**: `grep -rn "clause_uuid\|\.event_id"`
    over the twelve packaged modules shows their only consumer is `Scenario.as_json()`
    (`scenario.py:177-178`), and the demo path emits `ResolvedScenario.as_json()`
    (`gate_run.py:731`), which does not carry them. They are dead fields carrying
    unseeded values.
- **What would have caught it:** NOTHING DOES, and one thing looks as though it should.
  `scenario._selfcheck()` (`scenario.py:130-142`) runs at import and would pass under every
  variation of this: it compares the uuid5 derivation with the `EXPECTED` literals — the
  module against itself — and has never had any relationship to a seed or to Terraform.
  It is the canonical "guard that guards nothing" and it is still in the tree.

### F-4 `MAINLINE_DEMO_DATABASE` is the same name in three layers with no path between them — severity: LOW

- **Divergence:** `infra/modules/demo-api/main.tf:146` publishes it from
  `var.demo_database` (default `mainline_demo`, `variables.tf:237`) · `scripts/deploy/deploy.sh:159`
  reads a **shell** variable of the identical name (`DEMO_DATABASE="${MAINLINE_DEMO_DATABASE:-mainline_demo}"`)
  and asserts the live Cloud cluster against it at `deploy.sh:626-645` · `deploy.sh:911-918`
  (`TF_VARS`) passes no `-var demo_database=`, and `infra/envs/demo/variables.tf` declares
  no `demo_database`.
- **Command:** `grep -rn "environ.*MAINLINE_DEMO_DATABASE\|getenv.*MAINLINE_DEMO_DATABASE" --include=*.py .`
  and `grep -n "demo_database" infra/envs/demo/*.tf`
- **Output:** *(both empty — no Python module reads it; the root neither declares nor passes it)*
- **What a user or judge sees:** an operator running
  `MAINLINE_DEMO_DATABASE=mainline_demo_v2 scripts/deploy/deploy.sh` gets a preflight that
  probes `mainline_demo_v2` and a Lambda whose published configuration says
  `mainline_demo`. Nothing fails, because the handler takes the database from the DSN and
  the published value is decorative — which is precisely why the disagreement can persist.
- **What would have caught it:** NOTHING DOES. `main.tf:139-142` asserts that "`/v1/health`
  reports the database it actually reached, and a disagreement between the two is a
  finding" — that comparison is performed by no code: `health.py` reports
  `current_database()` and never reads this variable.

### F-5 The failure-diagnosis instruction for a 404 at `/` names an output the shipping root does not emit — severity: LOW

- **Divergence:** `infra/modules/demo-api/outputs.tf:119` declares `output "web_root"` and
  `infra/modules/demo-api/README.md` says it exists "to let a deploy catch here" ·
  `infra/envs/demo/outputs.tf` re-exports 17 outputs and `web_root` is not one of them ·
  `scripts/deploy/deploy.sh:1122-1123` tells the deployer, at the moment `/` 404s, to
  "check `terraform output -raw web_root` against the zip".
- **Command:** `terraform -chdir=<scratch>/infra/envs/demo output -raw web_root`, plus the
  root output list taken from the plan JSON's `output_changes`.
- **Output:**
  ```
  Warning: No outputs found
  ROOT OUTPUTS in plan: ['api_authorization_type', 'api_enabled', 'api_function_name',
   'api_function_url', 'api_function_url_domain', 'aws_account_id', 'aws_region',
   'cloudfront_invoke_grant_created', 'demo_url', 'demo_url_source', 'deploy_summary',
   'distribution_arn', 'distribution_domain_name', 'distribution_id',
   'dsn_parameter_name', 'enable_cloudfront', 'site_bucket']
  ```
- **What a user or judge sees:** the deployer, staring at a 404 on the demo hostname,
  runs the one command the script told them to run and gets a warning instead of a value.
- **What would have caught it:** NOTHING DOES. The underlying agreement is genuinely held
  (`deploy.sh:565-579`, `:853-855` compare the manifest's `web_root` with the literal
  `/var/task/web`, and the manifest measured `/var/task/web` while the zip really contains
  `web/index.html`); it is only the diagnosis path that is broken.

### F-6 Nothing in the repository reads what Terraform would publish — severity: LATENT (meta)

- **Divergence:** the publisher side is `infra/modules/demo-api/main.tf:135-201` and
  `:315-317`; the reader side is twelve Python modules. No artefact joins them.
- **Command:** `grep -rn "aws_lambda_function" --include=*.py . | grep -v "\.venv"`
- **Output:** *(empty — zero hits)*
- **What a user or judge sees:** the failure mode this whole wave exists to end. The
  environment contract has exactly two executable guards — `deploy.sh:484-493` for the SSM
  parameter name, and the `extra_environment` deny-list at `variables.tf:792-805` (which I
  verified is in step: `published - denied == []`). Every other name in the table above is
  held by prose in a README. The two tests that touch these names set them themselves —
  `test_demo_guard_anonymous.py:492` does `monkeypatch.setenv("MAINLINE_DEMO_ALLOW_MUTATION","1")`
  — which is precisely the "the test and the code draw on the same thing" shape.
- **What would have caught it:** NOTHING DOES. The check that would is cheap and does not
  exist: run `terraform show -json` on a plan, extract the one environment map, and assert
  it against a declared reader inventory in both directions. That is the command sequence
  in this document.

### F-7 The application's own configuration table documents 4 of the 12 names it reads — severity: LOW

- **Divergence:** `verticals/mainline/apps/demo-api/README.md:181-186` lists `MAINLINE_DSN`,
  `MAINLINE_DSN_PARAM`, `AWS_REGION`/`AWS_DEFAULT_REGION` and `MAINLINE_DEBUG` · the package
  additionally reads `MAINLINE_WEB_ROOT` (`static_site.py:157`),
  `MAINLINE_MAX_RESPONSE_BYTES` (`static_site.py:160`),
  `MAINLINE_DEMO_ALLOW_MUTATION` (`transitions.py:315`) and the six computed
  `MAINLINE_DEMO_<NAME>` names (`scenario.py:186,205-212`).
- **Command:** `sed -n '178,188p' verticals/mainline/apps/demo-api/README.md`
- **Output:** a four-row table whose last row is `MAINLINE_DEBUG`.
- **What a user or judge sees:** nothing directly. It matters because this is the document
  the Terraform author reads to learn what to publish, and the two names it omits that were
  load-bearing — `MAINLINE_DEMO_SIGNER_SUB` and `MAINLINE_DEMO_COUNTERSIGNER_SUB` — are
  exactly the two that shipped unpublished until the current wave.
- **What would have caught it:** NOTHING DOES.

---

## Pairs checked and found to agree, with the mechanism that holds them

* **`MAINLINE_DSN_PARAM` (published) ↔ the SSM name `deploy.sh` writes.** Plan says
  `/mainline/demo/cockroach_dsn`; `deploy.sh:157` sets the same constant and `:484-493`
  parses `infra/envs/demo/variables.tf`'s `default` and refuses a mismatch at preflight,
  before the state bucket exists. **HELD by an executed assertion.** (The module's own
  default `/mainline/demo/dsn`, `variables.tf:160`, is never used — the root always passes
  its own, and `deploy.sh:909` passes it again. Already recorded as W3-F5 in
  `docs/verify/deploy/secrets-and-blast-radius.md:477`; not re-raised here.)
* **`MAINLINE_WEB_ROOT` (published `/var/task/web`) ↔ the package layout.** Measured:
  the zip's top-level entries are `web` (114), `psycopg` (85), `psycopg_binary.libs` (16),
  `mainline_demo_api` (12), …; `web/index.html` is present; the build manifest declares
  `web_root = /var/task/web`. **HELD by `deploy.sh:565-579` and `:853-855`.**
* **The module's environment keys ↔ the `extra_environment` deny-list.** Executed against
  the plan JSON: the eight published keys are a strict subset of the nine denied names, so
  the `merge()` last-wins shadowing hole `variables.tf:780-787` describes is closed today.
  **HELD by a plan-time `validation`.**
* **Lambda reserved names.** `variables.tf:807-816` refuses all sixteen; the plan publishes
  none of them; `db.py:170-172,283` reads five and gets them from the runtime. **HELD.**
* **`demo_signer_sub != demo_countersigner_sub`.** `main.tf:367` precondition, backed by
  `0066_disposition.sql:176`. Real, but it is a *shape* check: it would pass on any pair of
  distinct strings, including a pair neither of which is in
  `mainline.signing_credential`. Recorded as LATENT rows 4 and 5, not as HELD.
* **No second environment publisher exists.** `grep -rn "aws_lambda\|environment" infra/modules/demo-site/*.tf` → empty; the plan contains exactly one `aws_lambda_function`.

## Not reached (and why)

* **A live deployed Lambda.** There is none: `aws lambda get-function-configuration
  --function-name mainline-demo-api --region ap-southeast-1` →
  `ResourceNotFoundException: Function not found`. The plan JSON is therefore the strongest
  available statement of layer 3, and it is what this report used. Nothing mutating was run.
* **The `enable_cloudfront = true` shape (22 resources).** It publishes the same
  `local.environment` map — only `url_authorization_type` and the invoke grant change — and
  `demo-site` contains no environment publisher at all, so the contract is identical. Not
  re-planned.
* **Whether `demo.signer` / `demo.countersigner` are the right principals in the *Cloud*
  database.** That is W1's and W2's question (`demo_world.sql:125,133` seeds those exact
  strings; `credentials.resolve_credential_id` looks them up by `signer_sub`). This report
  owns only the fact that the values now reach the process and that **nothing** holds them
  against the seed.
* **Which of the client-supplied disposition columns are projected away** beyond `site_id`.
  I settled `site_id` because an unpublished env name depends on it; the rest of that
  question belongs to the census lead's §2.6 and to W2.
* **A world chained from scratch by this analyst.** `d_w3_env_contract` was created on the
  local node as the brief allows, but the node is under heavy contention from the concurrent
  wave (a bare `SHOW DATABASES` took over two minutes), so chaining 271 migrations into it
  was not attempted. Instead the identifier and trigger checks in F-3 were run **read-only
  against three worlds another worker had already chained and seeded** — `w_w1_demo`,
  `w_w3_demotruth`, `w3_demo_api_123396ff6486` — which agreed with each other line for line.
  Nothing was written to any of them.
