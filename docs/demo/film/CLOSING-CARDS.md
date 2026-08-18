<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# THE CLOSING CARDS — you do NOT film these

**Your screen recording ends at B10, 2:28.** The last twenty-four seconds are three cards plus an
end card, and they are made in the edit. There is no screen to point a camera at.

## THE CARDS ARE ALREADY BUILT — you just record them

**`closing-cards.html` sits beside this file.** Open it in the browser you have been filming in,
press `F11` for full screen, then:

1. **Start your recorder.**
2. **Press `SPACE`.** The four cards play themselves, on the exact timings: 6 s, 10 s, 6 s, 2 s.
3. **Stop after 24 seconds.**

That is the whole closing sequence, in one take, with nothing retyped by hand.

`←` and `→` step through manually if you would rather hold each one and cut them yourself.
`H` hides the help line at the bottom — **press it before you record.**

> **`k1` is meant to sit over live picture.** If you have time in the edit, lay its three words
> over your B3 memory-loop footage. If you do not, the card on its own is fine and claims nothing
> different. Do not spend your last hour on it.

---

## The text, for reference

If you would rather build the cards in your editor, everything is below.

Every word below is transcribed from `ONSCREEN-TEXT.yaml`, which is the version of record. **Do
not retype from memory and do not paraphrase** — several of these lines are the honesty
disclosures the whole entry rests on, and they have been cleared word for word.

---

## k1 · THE LOOP · 2:28 – 2:34 · 6 s

**This one needs picture underneath.** It is an overlay over live footage, not a full card.
Reuse your **B3** memory-loop footage and lay the three words over it.

**`k1.overlay.columns`**

```
S T O R E                      R E T R I E V E                 A C T

mainline.event                 mainline_meas.recall_run        mainline.permit
mainline.blame_edge            mainline.clause_blame_current   CHECK gate_closed_when_issued
mainline.clause_blame_closure    (view · DISTINCT ON, gen DESC)  -> 23514
  append-only, generation-                                     mainline.fn_permit_merge_gate
  versioned; superseded,                                         -> P0001
  never deleted

occurred_at                    started_at                      refused at
2019-03-14T06:20:00Z           2026-08-02T03:00:00Z            <THIS RUN>

                               obligation materialised
                               2026-08-02T03:00:10Z
                               ten seconds
```

**`k1.overlay.strap`**

```
every date above is a column value · no AS OF SYSTEM TIME produced any frame of this film
```

---

## k2 · THE STACK · 2:34 – 2:44 · 10 s

**A full card, two columns side by side.** AWS on the left, CockroachDB on the right.

**`k2.overlay.aws_column`**

```
AWS  ·  IN THIS REQUEST

  AWS Lambda                  arm64 · mainline-demo-api
  Lambda Function URL         authorization_type = NONE   (the founder's explicit choice)
  SSM Parameter Store         /mainline/demo/cockroach_dsn
  AWS IAM                     one execution role; one inline policy, GetParameter on that one name


AWS  ·  IN THE APPLY THAT CREATED IT        24 created · 0 changed · 0 destroyed

  Amazon S3                   Terraform state · versioned · SSE-S3 · public access blocked
  CloudWatch alarms + SNS     the cost guard: three alarms on three timescales into one topic,
  + AWS Budgets               a responder that sets reserved concurrency to zero, and the budget


  Amazon Bedrock  —  EXERCISED IN THIS REPOSITORY.  IT IS NOT IN THIS REQUEST PATH.
  Claude on au.* inference profiles and Titan v2 embeddings, ap-southeast-2 (Sydney).
  The database is aws-ap-southeast-1 (Singapore).  There is no end-to-end Australian residency and we do not claim one.
  The refusal you just watched involved no model at all, and that is the point.
```

**`k2.overlay.cockroachdb_column`**

```
CockroachDB  ·  IN THIS REQUEST                 CockroachDB  ·  IN THIS DATABASE, EARLIER

CockroachDB Cloud (Basic)                       mainline.fn_check_project
  aws-ap-southeast-1 (Singapore)                  a PL/pgSQL trigger function. It overwrote
  CCL v26.2.5                                     this obligation's severity and virulence
  read live from GET /v1/health, not typed        from the blame closure when the row was
                                                  written. The gate reads its output.
SERIALIZABLE                                      It did not run in this request.
  one transaction, three savepoints,
  rolled back                                   recursive CTE  (WITH RECURSIVE)
                                                  the blame-closure writer,
CHECK constraint                                  db/queries/closure_write.sql:152.
  gate_closed_when_issued        -> 23514         THIS world's closure row carries
                                                  computed_by = demo_world.sql
PL/pgSQL trigger function                         projector_ver = demo-1.
  mainline.fn_permit_merge_gate  -> P0001         It did not run in this request.

user-defined enum                               42501
  mainline.subject_state                          read back by this same client during the
  ((state != 'merged':::mainline.subject_state)   deploy, one HTTP request at a time; and
   OR (open_blocking = 0:::INT8))                 256/256 ungranted pairs refused in
  the enum is inside the refusal message           privilege conformance.
                                                  It did not run in this request.
composite foreign keys
  blocking_check -> clause_version
    (clause_uuid, commit_id)
  permit_event -> subject_transition
    (subject_kind, from_state, to_state)


One cluster.  One region.  This repository holds no load profile, and we do not claim scale.
```

---

## k3 · THE LIMIT, THE RAIL, THE URLs · 2:44 – 2:50 · 6 s

**A full card.** The limit first — it is the line the voice speaks — then the rest.

**`k3.overlay.limit`**

```
THE LIMIT WE WILL NOT DRESS UP

Nothing in this data model separates a considered disposition from a rubber stamp.
It makes the question unavoidable, the record precise, the worst stamp non-representable.
We measure deliberation and never threshold it.
```

**`k3.overlay.rail_all_four`**

```
"what makes agentic systems different from traditional apps?"
   -> the database is in the reasoning loop, as the thing that constrains the agent

"Does the agent use the tools correctly and safely?"
   -> persisted: false — this call is non-mutating by construction

"Is it used for more than toy queries ... at real scale?"
   -> transactional state, read inside the same SERIALIZABLE transaction as the decision
      — and no scale is claimed

"resilience, access control, and what happens when things go wrong?"
   -> the refusal itself; 42501 on 256/256 ungranted pairs in privilege
      conformance; a ledger that publishes what did not run
```

**`k3.overlay.tools`**

```
------------------------------------------------------------------------------------------------
COCKROACHDB  ·  THE FOUR CONTEST TOOLS.  THE RULES REQUIRE TWO.   three EXERCISED, one DESIGNED

Distributed Vector Indexing (C-SPANN)  EXERCISED  3 cspann, 4 VECTOR, 42809    evidence/aws/ann/
Managed MCP Server                     EXERCISED  15 of 16, DIVERGED, published   evidence/mcp/
CockroachDB Cloud + ccloud CLI         EXERCISED  cluster list -o json, parsed   evidence/ccloud/
CockroachDB Agent Skills               DESIGNED   shipped, validated;  NO RUN IS COMMITTED  skills/
```

**`k3.overlay.urls`**

```
github.com/Shaugato/mainline
https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws
```

---

## end card · 2:50 – 2:52 · 2 s

Two seconds. Black, or the URLs held. Nothing moves.

---

## The one rule for all three

**Every line here has been cleared as true.** `k2` says Bedrock is *not* in the request path and
that no Australian residency is claimed. `k3` says nothing separates a considered decision from a
rubber stamp, and that Agent Skills is DESIGNED with no run committed. Those sentences cost the
entry nothing and buy it everything — a judge who sees a project name its own limits, unprompted,
in its closing seconds, believes the rest of it.

**Do not trim them to fit.** If a card is too full, make the type smaller or hold it longer.
