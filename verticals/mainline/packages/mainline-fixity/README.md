<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# mainline-fixity — the fixity patrol

**Agent 6 of the fleet** (`ARCHITECTURE.md` §8.4, §5.8). Tier **T1**. SQL role
`agent_patroller`. **No model.**

Its one job: compare what the procedure *says* against what the plant *does*, and
write down both the answer and the limits of the answer.

---

## The three sentences that shape the package

**A drift finding is a `control_delta` whose author is the plant.**
The comparison is not a new algorithm. It is `mainline_domain.lattice.explain`
with `reference = documented_cat` and `descendant = observed_cat` — the same nine
rules, the same join, the same minimal unsatisfiable subset the clause pipeline
uses. Because the merge gate already auto-materialises a blocking check for
`weaken` over severity ≥ 4 ancestry, **a reality-authored weakening fires the
existing gate with no new gate logic**, and because the blocking decision reads
`clause_blame_current.max_severity` rather than the clause's current text,
diachronic gating is preserved for free.

**"No excursion found" is never "no excursion occurred".**
A PI historian applies exception reporting at the collector and swinging-door
compression at the archive, so an archived value is a *vertex of a compression
corridor*, not a measurement. A difference smaller than `ExcDev + CompDev` is
recorded as a **bounded negative with its arithmetic** and the finding is marked
`undetermined`. `BoundedNegative.statement()` is the sentence a reviewer reads,
and it ends by saying what it does not establish.

**UNKNOWN is first class.**
A bisect that terminates against a skipped region returns a **range** —
`bisect_lo` and `bisect_hi` populated, `culprit_elem` NULL. `BisectOutcome`
refuses at construction to hold both a culprit and a range, so there is no shape
of the result that lets a reader take the name and drop the width.

---

## Why there is no model here

`ARCHITECTURE.md` §8.4 row 6 names the decision this agent does **not** make:
`weaken` — *the lattice compare decides, and abstain ⇒ weaken*. The comparison is
therefore pure code over two structured tuples, and there is nothing left for a
model to do. Three consequences, each mechanical rather than promised:

| Claim | Enforced by |
|---|---|
| no model SDK is reachable from this package | `pyproject.toml` has one dependency, and `tests/unit/fixity/test_starvation.py` walks every module's AST |
| no `UPDATE` or `DELETE` statement exists | `emit.STATEMENTS` is regex-asserted by the same test; `agent_patroller` holds `INSERT` only, so such a statement could only ever be refused |
| no gate table is read at a stale timestamp | `follower.assert_patrol_safe` refuses any statement naming a table in `GATE_TABLES`, and any `SELECT` without the follower-read preamble |

The last one is the interesting one. §9 says patrol reads use
`AS OF SYSTEM TIME follower_read_timestamp()` **and** that gate reads never use
follower reads. Read together they forbid exactly one thing — a stale read of a
gate table — and that combination is refused at statement-construction time
rather than in review.

---

## The two projected columns

`drift_finding.severity_inherited` is projected from `clause_blame_current`, and
`gate_class` is derived from it. Both are `NOT NULL`, so the insert must supply
*something*. What it supplies is `projection_placeholder(direction, undetermined)`
— a pure function of those two arguments and of **nothing else**. It never sees a
severity, a blame closure or an ancestry, so it cannot smuggle one; and if the
projection trigger were ever missing, a real weakening lands as `(5, 'blocking')`
— loud, and wrong in the safe direction — rather than as a quiet `advisory`.

This is the same shape conformance case **CF-07** tests on `blocking_check`: the
client claims a value, `fn_check_project` overwrites it, and the claim was never
load-bearing.

---

## What this package does *not* fix

**An `undetermined` finding does not block.** MI21 (`CHECK
undetermined_never_blocks`, `23514`) says so, and that is right — a permit must
not be refused because a historian tag was out of service. But it means an
adversary who can make a comparison undetermined has, by that route alone,
avoided the drift gate.

The answer is not to make undetermined findings blocking. It is that an absence
never goes to the drift gate at all: it opens an **A6 discordance warrant**
("verification obligation window elapsed with no evidence row" — S27, and the
class most real drift belongs to), which **MI05** makes blocking at merge through
a different mechanism, with a different constraint name, closed by a person
rather than by a patrol. The finding is advisory; the obligation is not.

That is a real mitigation and it is not a complete one. A site that never
configures the verification obligation in the first place has no window to elapse
and gets no A6. **This package cannot detect a control nobody ever asked to be
verified.** Coverage of the obligation set is the corpus's problem, not the
patrol's, and we do not claim otherwise.

**We never speak OPC UA to a control system.** Everything arrives as a periodic
one-way export into an S3 landing zone from the OT DMZ. `observed_assertion.source_ref`
is the S3 `versionId` of that export and is required even in fixtures — a fixture
with an empty provenance field trains everyone to accept an empty provenance field.

---

## The changepoint detector, and why it uses exact arithmetic

`bisect.pelt` is Pruned Exact Linear Time changepoint detection with an L2 cost,
computed over `fractions.Fraction` prefix sums. Not floats. A changepoint that
moved because of floating-point summation order would be a culprit that changed
between two runs of the same patrol over the same data — and this is a record a
lawyer reads.

The penalty is `DEFAULT_PENALTY = Fraction(1)`, with its derivation in the
docstring: for a 0/1 compliance indicator, an isolated single flip has a maximum
cost reduction approaching 1, and splitting it out costs `2·penalty`, so a penalty
of 1 suppresses isolated flips and admits a sustained run of two or more. A patrol
whose sensitivity is a magic constant cannot be cross-examined about its
sensitivity.

`bracket_last_regression` takes `worse={'higher','lower'}` from the parameter's
**ratified** `safe_direction`, never from the shape of the data. A detector that
decided for itself which end was bad would be deciding a safety question from a
histogram.

---

## Unverified on the target platform

`BEGIN; SET TRANSACTION AS OF SYSTEM TIME follower_read_timestamp();` is the
documented CockroachDB idiom and is what `follower.PATROL_READ_PREAMBLE` emits.
That `cluster_logical_timestamp()` inside such a transaction returns *that
transaction's* read timestamp — which is how `patrol_run.as_of_hlc` is populated —
is documented behaviour that **this repository has not measured on v26.2**. The
assertion lives in `tests/integration/fixity` and skips with a reason until a
cluster is available. Nothing in this package or its docstrings claims it has been
observed.

The tables this package writes (`patrol_run`, `drift_finding`,
`observed_assertion`, `time_witness`, `discordance_warrant`) are migrations
`0090–0098`, which belong to the data-model lead and had not landed when this
package was written. The unit suite is complete and passes offline; the
integration lane skips with a reason until those migrations exist.
