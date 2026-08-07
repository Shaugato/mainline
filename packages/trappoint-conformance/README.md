<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# `trappoint-conformance`

The runner for the TRAPPOINT conformance suite. Illegal histories, each asserting an
**exact SQLSTATE** and an **exact exhibit name**.

```bash
uv run --package trappoint-conformance trappoint-conform --profile trappoint-ref --list        # no database needed
uv run --package trappoint-conformance trappoint-conform --dsn "$LOCAL_DSN" --profile trappoint-ref
```

> **This package currently ships one case and that case fails.** `CF-01` is red because
> the schema that would satisfy it does not exist yet. That is `PL-2` working, not a
> defect: *for a product whose deliverable is a refusal, a suite that has never been red
> asserts nothing.* See [`docs/adr/0005-red-before-green.md`](../../docs/adr/0005-red-before-green.md).

---

## What the runner is, and is not

It is a **skeleton**. `spec/conformance/manifest.toml` is the single source of truth —
seventy-one cases, forty-five of them on the `trappoint-ref` profile — and this package
supplies the four things every case needs, plus `CF-01` as the worked example:

| Piece | File | What it guarantees |
|---|---|---|
| Manifest reader | `manifest.py` | Nothing is defaulted, inferred or repaired. An empty `expect_constraint` is a broken manifest, reported as one. |
| SQLSTATE classifier | `sqlstate.py` | The taxonomy is **total**. There is no `UNKNOWN` member; an unmodelled code raises. |
| Tenancy isolation | `site.py` | A deterministic `site_id` per (run, case), so the suite parallelises and a re-run lands on the same rows. |
| History harness | `harness.py` | `assert_refusal(history, sqlstate, constraint)`, the `40001`-only retry, and the exhibit-weakening record. |

The remaining seventy cases, the unwelding matrix, `ANOMALY_COVERAGE.md`,
`REFUSAL_DEPTH.md` and `test_manifest_totality` belong to the conformance-corpus worker.
Cases with no implementation are reported as **PENDING** — printed and counted, never
silently absent.

---

## The five result states

The distinctions are the reporting contract, and three of them exist because collapsing
them would let a suite pass by accident.

| State | Meaning | Fatal? |
|---|---|---|
| `PASSED` | the database refused exactly as the manifest says it must | — |
| `FAILED` | it did not. **Includes the ordinary pre-migration state**, where the relation the case needs does not exist — reported as a failure *naming the missing object*, never as a harness error | yes |
| `SKIPPED` | the case declares a `requires` capability this profile does not supply | no, but never counted as a pass |
| `PENDING` | the manifest declares the case; no implementation exists yet | not yet — `test_manifest_totality` makes it fatal once the corpus lands |
| `ERROR` | the runner could not run the case at all | yes |

**A red case and a broken runner must not look alike.** That is why `42P01` is
classified as *schema absent* and surfaces as `SCHEMA NOT MIGRATED — expected 23514 on
'gate_closed_when_issued'; observed 42P01 …`, rather than as an anonymous crash. And why
"cannot connect" exits through its own path with its own sentence: *"there was no
database"* and *"the database said no"* are different claims.

---

## The exhibit, and when it is weakened

`spec/errors.md` §3.1: for `23514`/`23503`/`23505` the exhibit is
`diag.constraint_name`, verbatim. For `P0001` that field is **empty by construction**,
so the exhibit is the fully-qualified name of the raising object.

Where the driver cannot supply it, the harness recovers what it can from the message
prefix convention (`MAINLINE:` / `TRAPPOINT:`) and sets `exhibit_weakened = True`. That
flag is printed and appears in `--json`. **A run whose exhibits were inferred is never
indistinguishable from a run whose exhibits were reported** — which is the difference
between a diagnosis and a guess dressed as one.

---

## Isolation is a fresh tenancy, not a rollback

Cases get a deterministic `site_id = uuid5(namespace, f"{run_id}:{case_id}")`. Three
reasons, and the third forces it:

1. the suite parallelises against one cluster;
2. several objects under test are **append-only**, so a suite that cleaned up after
   itself would exercise a delete path the product refuses to have;
3. row-level security is scoped by `site_id`, and a suite sharing one site would be
   testing the gate with the security model switched off.

Determinism matters for a fourth, practical reason: a failing case re-run on its own
lands in exactly the same tenancy, so the rows it left are the rows you inspect. Set
`TRAPPOINT_CONFORM_RUN_ID` to pin a whole run.

Nothing is torn down. Disposal is the container's job (`just nuke`), and it is the only
disposal the unwelding harness may use.

---

## What a green run entitles you to claim

Quoted from `spec/conformance/README.md` §9, because the boundary is the point:

**It does entitle you to say** the database refused every history this specification
says it must refuse, by the exact mechanism it names, at the named profile and version,
and that no refusal fell outside the modelled taxonomy.

**It does not entitle you to say** that the vertical's obligations are the right
obligations; that severity was scored correctly; that a disposition is honest; that
retrieval was exhaustive; or that any human process improved.

A claim of conformance **must cite version and profile**. The summary line carries both:

```
1/45 · spec 1.0.0-rc.1 · profile trappoint-ref · failed 0 · pending 44
```

A claim without a profile is not a claim.

## Licence

Apache-2.0. Part of the TRAPPOINT substrate.
