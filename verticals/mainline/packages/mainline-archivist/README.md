<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# mainline-archivist

**The Archivist — ingest and appraise** (`ARCHITECTURE.md` §8.4, row 1).

> Every field of an event row is a coded fact, a verbatim span read out of the source, or
> a model rating capped one below the arming threshold.

That is the whole package. The rest of this file is the evidence for each third of it.

---

## The decision this agent does not make

§8.4 gives every agent in the fleet a decision it is not allowed to make. The Archivist's
is **severity**:

> Severity. It comes from a coded field, a regulator classification, or a signed human. A
> model-rated severity never arms the gate.

Migration `0033_event.sql` turns that sentence into a plain-column CHECK:

```sql
CONSTRAINT model_cannot_arm CHECK (severity_gate < 4 OR severity_basis <> 'model_rated')
```

`mainline_archivist.appraise` is the arithmetic that makes a row satisfying that CHECK the
only row this package can build. The important part is what it does **not** do: it does
not zero the model's reading.

| | value |
|---|---|
| a model rates the incident | 5 |
| `severity_potential` on the row | **5** |
| `severity_gate` on the row | **3** |
| `severity_basis` | `model_rated` |
| `silence_ledger` row written | `source='severity_downgrade'`, `reason='cap_exceeded'` |

The disagreement between what the machine thought and what the gate did is *in the
record*, quotable, with the profile id and prompt version of the call that produced it.
0033 says why in its own header: **that row is a better exhibit than a green test suite.**

A model rating can still become a gate-arming severity — by `promote()`, which demands a
person id and a `signing_credential` id, and which keeps the model's evidence on the
promoted claim. A promotion nobody signed is the original problem with a different
`severity_basis` string.

---

## Where the model call sits in the posture

`mainline_quarantine.pipeline.intake` is a one-shot evaluator: it takes the payload a
*fully compromised* model would return and reports what the deterministic layers do with
it. A live agent cannot use it that way, because it has to make the call in the middle.
So `ingest_document` runs the layers directly, in firing order:

```
L5  capability starvation      before a byte is read
L2  delimit, datamark, screen
    ── triage and extraction, both quarantined_call() ──
L3  output-schema containment  over what came back
L4  semantic anchoring         over what came back
L6  every non-clean verdict becomes a finding
```

The sequence taken is recorded on `IngestOutcome.layers_fired`, and
`tests/unit/archivist/test_ingest.py` asserts it against `mainline_quarantine.FIRING_ORDER`
rather than against a literal — so a change to the posture's order fails there instead of
drifting.

`L1` is not in that list because it is not a step. It is the shape of
`mainline_agentkit.call.quarantined_call`, which has no `tools` parameter, and it is
proved by `scripts/agents/assert_no_tool_construction.py` over the whole tree. This
package's suite invokes that script against this package rather than reimplementing it.

---

## Grants I do not hold

`agent_ingestor` has `INSERT` on eleven tables and nothing else — no `UPDATE`, no
`DELETE`, anywhere. `assert_ingest_safe` refuses any statement outside that list before a
connection is opened, and every statement this package builds goes through it.

Two things the Archivist produces but **cannot write**:

* **`mainline_meas.silence_ledger`.** Decision A8 says a model refusal is a row, and
  invariant I13 says a capped severity is a row. `GRANTS.yaml` gives `INSERT` on that
  table to `agent_recaller` only. The rows are built here — correctly, through
  `mainline_agentkit.refusal.SilenceRow`, which validates both CHECK vocabularies at
  construction — and returned on `IngestOutcome.silences` for a caller that holds the
  grant. **This is a real gap in the grant matrix, not a design choice of this package**,
  and it is raised as a cross-domain note rather than worked around.
* **`mainline.document_intake_finding`.** The role *does* hold the INSERT, but the DDL
  does not exist yet: `GRANTS.yaml` records it as a DM-16 orphan (§11.2 grants it, §5
  never defined it) and `dm-periphery` owns creating it. `insert_intake_finding` therefore
  derives its column list from `DocumentIntakeFinding.to_row()` — quarantine's own
  authoritative statement of the row's shape — instead of declaring a column order this
  package would be inventing.

---

## What is not verified

* **The S3 and Textract legs have never been executed.** AWS credentials are not valid on
  the build machine (PL-3, 2026-08-09). `S3ObjectStore` and `TextractExtractor` are behind
  the `aws` extra with their `boto3` imports inside the methods that use them. What is
  claimed for them is that the call shapes match the published APIs — `GetObject` with a
  `VersionId`, `DetectDocumentText` with an `S3Object` — not that they have been observed
  to work. `LocalObjectStore` and `Utf8TextExtractor` are the offline path and they are
  real code, not doubles: the demo corpus reads through them.
* **The multi-page Textract flow is not implemented.** `StartDocumentTextDetection` +
  `GetDocumentTextDetection`, with its job polling, is recorded as deferred rather than
  stubbed. A polling loop nobody has run against the service is a worse lie than an
  absence.
* **No statement in this package has been executed against a cluster.** The column lists
  are transcribed from migrations `0033` and `0035` and asserted against them by
  placeholder count and vocabulary, which is a check of transcription, not of execution.

---

## Using it

```python
from mainline_agentkit.runtime import boot_runtime
from mainline_quarantine import FleetRegister, LocalPromptAttackScreen

from mainline_archivist import (
    CodedFacts,
    LocalObjectStore,
    ObjectRef,
    SeverityClaim,
    Utf8TextExtractor,
    ingest_document,
)

store = LocalObjectStore(root=incident_dir)
obj = store.fetch(ObjectRef(object_key="incidents/IR-2019-0117.txt"))
text = Utf8TextExtractor().extract(obj)

outcome = ingest_document(
    runtime=boot_runtime(inference_profile_arn=profile_arn),
    obj=obj,
    extracted=text,
    coded=CodedFacts(
        site_id=site_id,
        kind="incident",  # coded, never a triage route
        occurred_at=occurred_at,
        title_quote="INCIDENT INVESTIGATION REPORT IR-2019-0117",
        narrative_span=(212, 331),
        claims=(SeverityClaim.coded(3, field_name="consequence_class_actual", span=span),),
    ),
    screen=LocalPromptAttackScreen(),
    register=FleetRegister.from_yaml_path(fleet_yaml),
)

with connection.cursor() as cursor:  # the caller holds agent_ingestor
    for statement in outcome.statements:
        cursor.execute(statement.sql, statement.params)
```

`outcome.silences` still has rows to write through a role that holds them, and
`outcome.provenance` is what goes into `agent_action_provenance`.

---

## Tests

```
tests/unit/archivist/test_appraise.py    the severity discipline, from both directions
tests/unit/archivist/test_verbatim.py    a model supplies characters; we supply offsets
tests/unit/archivist/test_emit.py        statements, vocabularies, and the eleven tables
tests/unit/archivist/test_ingest.py      one document through the whole posture
tests/unit/archivist/test_starvation.py  what this package does not hold, over its own AST
```

The suite needs no cluster, no AWS account and no installed distribution: the workspace
member is put on `sys.path` by the directory's `conftest.py`, and every socket call from
the suite raises.

**PL-2, observed.** With `MODEL_GATE_CEILING` set to `ARMING_THRESHOLD` instead of
`ARMING_THRESHOLD - 1`, three tests fail — `test_the_ceiling_is_one_below_the_arming_threshold`,
`test_model_rating_of_five_lands_at_three` and `test_the_capped_reading_is_a_row_not_a_shrug` —
and the second fails with `ModelRatedCannotArm: appraisal produced severity_gate=4 on
basis 'model_rated'`, raised by the last-line-of-defence check in `appraise()`. The suite
has been red for the right reason before it was green.
