<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# `disposition_ext` — the counsel-gated surface, as configuration

**This directory is not in the apply path.** Nothing here is a migration, nothing here has a
number, and `trappoint migrate` never discovers it. It is the switchable surface of gate **G0**,
and it exists so that when the legal answer arrives the change is a *policy value*, not a
migration.

---

## What G0 is

`BUILD_PLAN.md` §2 defines **G0** as a paid one-hour consultation with an Australian
resources-sector WHS/safety lawyer, putting four questions. The two that decide the shape of this
directory:

> Does a signed, named `mechanism_absent` disposition against a fatality-linked precursor, made 48
> hours before an incident, **help or hurt the defence** relative to no record existing at all —
> and does the answer change if the system also logs every precursor it declined to surface, with
> its arithmetic?

> Does per-approver dwell timing constitute computer surveillance requiring notice under the NSW
> Workplace Surveillance Act 2005 or its analogues?

The gate exists because the adversarial audit named the disposition record as the project's single
largest unvalidated assumption, in both directions at once: a signed `mechanism_absent` preceding a
fatality is a conscious-disregard exhibit, and *declining to record whether the human read the
warning* is a worse exhibit, because that design choice is itself discoverable, dated and authored.

## What was decided

**G0 was not sought.** `docs/adr/0001-g0-counsel.md` records the decision and executes the
**pre-committed conservative default**. The counsel hour is necessary for the commercial wedge and
for freezing the final legal shape of the disposition record; it is not necessary to build the
platform, to satisfy any hackathon requirement, or to demonstrate the gate. Idling the build on a
lawyer's diary would have been a schedule wound for no engineering gain.

**The build therefore proceeds in full and the DDL ships unconditionally** (data-model ruling
DM-17). There is **no variant DDL** and there will not be one: a DDL fork per legal answer is two
schemas to test and one to get wrong.

## The five counsel-gated files

| Migration | Object | Conservative reading applied |
|---|---|---|
| `0066_disposition.sql` | `mainline.disposition` | No `mechanism_absent` over fatal (severity ≥ 4) ancestry — enforced by `fk_clearance`, not by a flag |
| `0067_disposition_citation.sql` | `mainline.disposition_citation` | `evidence_opened` is recorded; citation is mandatory, not optional |
| `0068_override_ledger.sql` | `mainline.override_ledger` | Ships; override stays site- and signer-scoped and monotone |
| `0069_carried_disposition.sql` | `mainline.carried_disposition` | Ships with a bounded-window constraint, and with a composite `fk_clearance` so the three absent cells are absent from *carrying* as well as from *signing* |
| `0086` (recall band) | `mainline_meas.silence_ledger` | Ships **unprivileged**, in the `mainline_meas` zone — treated as discoverable by default |

`0070_carried_disposition_use.sql` carries the same header because it is meaningless without
`0069`: it is the join that turns "we carried a verdict" from an assertion into a count.

## The conservative reading, in plain words

Three cells of the clearance lattice are **absent**, and absence is the mechanism. They are not
stricter rows with a higher rank and a shorter expiry — they are **no rows**, so the composite
foreign key `(virulence, kind) → mainline.clearance_legal` refuses them with `23503` for every
writer, including a DBA and including the read-mostly MCP path.

| Cell | Why it is absent |
|---|---|
| `(blood_fatal, mechanism_absent)` | There is no such thing as a control written by a fatality whose mechanism is absent. If the mechanism has genuinely gone, the clause is retired through a change request that inherits the same ancestry — not dismissed on a permit. |
| `(blood_fatal, accept_residual)` | Accepting residual risk on a control a death wrote is the exhibit that ends the argument. No rank, no countersignature and no expiry makes this cell legal. |
| `(blood_major, accept_residual)` | The one a customer may reasonably contest. It is versioned data with a named approver, so contesting it is an amendment carrying a signature rather than a code change — which is exactly the property the lattice exists to have. |

`clearance_legal.conservative.sql` in this directory is the executable statement of that reading:
it asserts the absence rather than creating anything.
`tests/integration/schema/test_mi_disposition_gated.py` runs it against a live v26.2 and, in the
same suite, signs and carries each absent cell to prove the refusal is real and names its
constraint.

### Known divergence, recorded rather than papered over

Both `mainline.disposition` and `mainline.carried_disposition` name their clearance foreign key
`fk_clearance`, and `mainline.carried_disposition` names its bounded-window and rationale-length
checks `bounded` and `substantive`. Specification rule **R-3 (Exhibit Uniqueness)** requires a
refusal-bearing name to be unique across the whole schema — the exhibit name alone must identify
the refusal without a qualifying table — and names the mirrors it expects:
`carried_bounded`, `carried_substantive`. `spec/conformance/manifest.toml` case **CF-66** carries
`expect_constraint = "carried_bounded"` as a literal string.

The mismatch is invisible today because CF-66 is skipped (its capability token is undeclared), so
it would surface as a conformance failure at the moment the corpus is turned on. It is carried as a
deliberately red test in `test_mi_disposition_gated.py`, naming the file and the owner, rather than
as a note nobody reads. The fix is a rename in
`verticals/mainline/db/migrations/0069_carried_disposition.sql`; nothing else in the tree
references either name.

**Per-approver dwell timing defaults to OFF.** `deliberation_seconds` is derived from the
server-issued `exposure_receipt.issued_at` — a record of what the *system* did, not a measurement
of a worker. Any per-person measurement family stays opt-in behind `person_measure_policy` and is
not enabled in the demo or in any default configuration.

**`silence_ledger` ships unprivileged.** It lives in `mainline_meas`, the zone with no gate
authority, and is treated as discoverable by default. A system that records what it declined to
surface, with the arithmetic, and then hides that record behind privilege has chosen the worst of
both worlds: it has the exhibit and it looks like it was concealing it.

## What is withheld until G0 clears

1. **No public claim about the paid MOC Ancestry Audit product** — not in the README, the
   submission, the video, or on any site.
2. **The `mainline-audit` policy package** (thresholds, the FSL side of the measurement family) is
   not published.

G0 must be answered **before** the first commercial conversation about the paid audit, before
publishing `mainline-audit`, before enabling any per-person measurement in a customer tenant, and
before freezing the disposition kind vocabulary as a SemVer-stable public API.

## Files in this directory

| File | What it is |
|---|---|
| `README.md` | this document |
| `disposition_ext.toml` | the three switch values, their defaults, and what flipping each one costs |
| `clearance_legal.conservative.sql` | an executable assertion that the three cells are still absent — `SELECT`-only, safe to run against production, and non-empty output means the conservative reading has been altered |

## How the switch is meant to be flipped

When G0 is answered and the answer differs from the default:

1. amend `disposition_ext.toml` — one value, with `decided_at`, `decided_by` and the advice
   reference filled in;
2. if the answer opens a lattice cell, that is an **`INSERT` into `mainline.clearance_legal` with a
   named `approved_by_sub` and a bumped `policy_version`** — a data amendment carrying a signature,
   which is the whole reason the lattice is a table;
3. re-run `clearance_legal.conservative.sql`; it now reports the opened cell, which is the intended
   and visible consequence;
4. no migration is written, no column changes, and no test that asserts *behaviour* has to be
   rewritten (DM-5).

Nothing in this directory is read at render time or at apply time today. It is a **declaration**,
and it is stated as one rather than pretending to a wiring that does not exist: the enforcement is
the absent rows in `0018b_clearance_legal_seed.sql` and the two foreign keys that point at them.
