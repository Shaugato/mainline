<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# mainline-cherrypick — the cherry-pick worker

**Agent 7 of the fleet** (`ARCHITECTURE.md` §8.4, §5.9). Tier **T1**. SQL role
`agent_fleet`. One model call, and it is a T2 narration that cannot resolve
anything.

A lesson learned at one plant is offered to its sister plants. What happens next
is the subject of this package, and the design decision underneath all of it is
that **sites are downstream distributions, not replicas**.

---

## Four sentences, and the mechanism behind each

### Only tightenings travel — and it is a `CHECK`, not a policy

`CHECK only_tightenings_travel` (MI23, `23514`) restricts `lesson.control_delta`
to `introduce`, `strengthen` and `restate`. Weakenings are site-local trade-offs
and must be re-earned locally: a setpoint that is right at one plant can be an
unrevealed hazard at another, so a relaxation one site justified with its own
evidence must not arrive at a sister site carrying that justification.

`Lesson.__post_init__` refuses to construct one, so the message names the lesson
and the delta rather than the constraint. `travel.assert_may_travel` runs again
inside `emit.insert_lesson`, immediately before the statement is built — the check
then applies to the object about to be written rather than to the object that was
once constructed.

### A mandated *response* beats mandated conformity

`propagation.declination_kind` has three values, each carrying the evidence that
makes it checkable later:

| kind | must carry | mirrored `CHECK` |
|---|---|---|
| `mitigated` | `already_present_clause` | `mitigated_names_local_clause` |
| `waiver` | `declination_expires_at` | `waiver_expires` |
| `mechanism_absent` | `declination_predicate_id` | `na_is_falsifiable` |

This is Debian's DEP-3 model, whose machine-readable `Forwarded: not-needed`
declination has been in production since 2009. A site is not required to conform;
it is required to **answer**, and an answer with nothing attached is a queue item
being closed. `adopt.reopen_expired_waiver` implements MI28's other half — *a
bounded window means bounded, not merely present* — so a waiver whose expiry has
passed stops being a declination and the site owes the fleet a fresh answer.

`already_present` is a state, not a decline, and that matters: a site that
independently wrote the same control is **convergent evidence for the lesson**,
and losing that to a generic "declined" would throw away the strongest datum in
the propagation.

### A recorded resolution is proposed, never auto-applied

Four independent barriers. Any one would do; all four means the claim survives
someone changing one of them without understanding it.

1. **Schema** — `ConflictNarration.resolution_proposed` is `Literal["none"]`, so a
   constrained decoder cannot emit anything else.
2. **Call shape** — `quarantined_call` has no `tools` parameter. The component
   reading two hostile safety documents holds no capability to act on them.
3. **Grant** — `agent_fleet` holds `INSERT` on `merge_conflict` and no `UPDATE`,
   so `resolved_commit`, `resolved_by` and `resolution_sig` are unreachable after
   insert. `emit.assert_fleet_safe` refuses any statement that assigns them.
4. **Type** — `HumanResolution` refuses an empty signature and refuses a subject
   matching `agent_`, `svc_`, `mainline-` or `system:`. The first way this
   guarantee would be lost is not an attack; it is a service account being given a
   friendly display name.

One less obvious choice: **the recalled resolution is withheld from the prompt.**
`rerere.recall` may have a remembered resolution for exactly this conflict shape,
and putting it in the trusted context would make echoing it the easiest completion
the model could produce — a recommendation, in prose, from a component forbidden
to recommend. The narration explains the disagreement; the recall is shown to the
person beside it, labelled as what it is.

### rerere, with recall

Git's `rerere` remembers **how** a conflict was resolved. It does not remember
**where the resolution came from**, so when a resolution turns out to have been
wrong, git cannot tell you which trees inherited it.

`resolution_memory.origin_conflict` closes that for the price of one column, and
`rerere.INHERITED_SITES_SQL` is the query it buys: given a resolution found wrong,
return every site that inherited it, with its propagation state, so the recall
notice goes to the sites that acted on it rather than to all of them.

`recall()` **raises** rather than returning `None` when the memory exists and has
been recalled. "There is no memory" and "the memory is known to be wrong" are
different facts, and the second is worth interrupting for.

---

## The score is not a model output

`propagation.score` is produced by `travel.applicability_score` — integer
arithmetic over four published weights in `SCORE_WEIGHTS`, summing to 1000. The
DDL column beside it is called `model_version`, and this package fills it with
`SCORER_VERSION = "fleet-applicability-scorer-1.0.0"`.

A column named for a model that holds a deterministic value is a far smaller lie
than a model in the propagation path — and the propagation path ends at a site
safety superintendent's queue, which is not a place a model's opinion should be
ordering things silently.

The score **decides nothing**. A site that receives a lesson scoring 12 still owes
the fleet an answer.

**`DEFAULT_SLA_DAYS` is not derived from any standard.** No regulation this project
has read prescribes a fleet-propagation response window. The table is a starting
point for a customer's own escalation policy, `due_by()` takes it as an argument,
and inventing a number and presenting it as best practice would be exactly the
unearned authority this product exists to refuse.

---

## `patch_digest`, and why it is keyed on `cat_key`

§5.9 specifies `patch_digest` as *sha256 over the NORMALISED delta set (git
patch-id)*. `git patch-id` strips line numbers and whitespace so the same change at
a different offset hashes the same. Ours strips one more thing: **site-local clause
identity**.

A `clause_uuid` means something only inside one site's document tree, so a delta
set keyed on it would give every site a different digest for the same control
change and `lesson.by_digest` would never hit. The set is keyed on `cat_key` —
identity axis 2, the hash of the *control the clause asserts* rather than of the
sentence it asserts it in — so two plants that wrote the same obligation in
entirely different prose produce the same element.

Sorted (a lesson is a set; document order is layout), deduplicated (the same change
twice in one document is a drafting artefact), and hashed over RFC 8785 canonical
bytes with a domain prefix. Never `sha256(jsonb::string)`: JSONB reorders keys and
`sha256` returns hex text, so a digest taken that way cannot be reproduced by a
stranger holding the same data.

---

## What the grant matrix decided for us

Three shapes in this package are consequences of
`verticals/mainline/db/GRANTS.yaml` rather than of taste, and they are worth
knowing before changing anything:

* **`MergeConflict` has no `resolved_*` fields.** A Python object able to carry a
  resolution would model a state this component can never produce, and someone
  would eventually write code assuming it could.
* **`advance()` emits an `UPDATE` that sets `state` alone.** §11.2 scopes
  `agent_fleet`'s `UPDATE` on `propagation` to `prop_state` by trigger.
  `open_conflicts` is a trigger-maintained projection over `merge_conflict` — the
  same shape as `permit.open_blocking` over `blocking_check` — so a site cannot
  declare itself conflict-free.
* **`conflict_silence_row()` returns a row this package cannot write.** Only
  `agent_recaller` holds `INSERT` on `mainline_meas.silence_ledger`. Returning it
  surfaces the boundary instead of hiding it behind a helper that would fail at run
  time with a `42501`.

The state `UPDATE` is a compare-and-set on the previous state
(`WHERE … AND state = %s`), because CockroachDB has **no advisory locks** and two
workers handed the same at-least-once delivery must not both advance the row.

---

## A clean merge is not approval

`merge3.merge3` is the classical diff3 of Khanna, Kunal and Pierce, on exact LCS
alignments with fixed tie-breaking so the same three inputs always yield the same
conflict set. A conflicted merge returns `merged = None`: git writes conflict
markers into the working tree, and a procedure containing `<<<<<<<` is a document a
person can commit by accident. `render_markers()` exists for display and says so.

A clean merge says the two edits did not touch the same lines. It does not say the
result is safe. Those are very different claims and this package only ever makes
the first.

---

## Deferred and unlanded

The tables this package writes (`lesson`, `propagation`, `merge_conflict`,
`resolution_memory`) are migrations `0094–0097`, which belong to the data-model
lead and had not landed when this package was written. The unit suite is complete
and passes offline with no network and no credential; the integration lane skips
with a reason until those migrations exist.

The full **M17 TRANSPORT WARRANT** — do-calculus transportability licensing
propagation, with `site_delta`, `transport_certificate` and an undeletable
escalating `conflictor` — is K7 and is **not built**. What is built is the
`propagation` spine it sits on, plus a declarative envelope predicate the
originating site writes. The envelope is not a transportability proof and this
package does not present it as one.
