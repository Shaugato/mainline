<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Glossary

**You are here:** the fixed vocabulary for the architecture document. Front door:
[`../ARCHITECTURE.md`](../ARCHITECTURE.md).

Twenty-four terms. Every one is glossed in plain language first, and the table, route or file
that makes it a real thing comes second. Nothing in the architecture chapters uses a term
before it appears here, and no chapter may contradict a gloss on this page.

If a term you hit is *not* on this list, the chapter that used it owes you a plain-language
gloss in the same sentence. If it did not give you one, that is a defect — report it.

---

<a id="permit"></a>
### permit

A written authorisation for one specific dangerous job, at one place, for one window of time.
Nobody starts work until it is issued. This is the ordinary industrial artefact — hot work,
confined space entry, breaking containment — not a metaphor.

Table `mainline.permit`, created by `verticals/mainline/db/migrations/0050_permit.sql`.

<a id="merge"></a>
### merge

Also called **issue**. The moment a permit stops being a draft and becomes an authorisation —
the moment after which people may start work.

Here that moment is exactly one database write: the permit row's `state` column becoming
`merged`. It is the write the [gate](#gate) defends. Everything else in this system exists to
make that one write refusable.

<a id="obligation"></a>
### obligation

Also called a **blocking check**. Something that must be settled before the permit may be
issued — typically a past incident that this job resembles, attached to this permit as a row.

An obligation is not advice and not a warning banner. While one is open, the issue write does
not succeed.

Table `mainline.blocking_check`, created by
`verticals/mainline/db/migrations/0058_blocking_check.sql`.

<a id="disposition"></a>
### disposition

The signed answer to exactly one [obligation](#obligation): a named competent person
recording what they did about it. One obligation, one disposition, one name attached.

A disposition is how an obligation gets closed. There is no other way to close one, and in
particular no way for the person raising the permit to close their own obligations by
asserting that the count is zero — see [projection](#projection).

Table `mainline.disposition`, created by `verticals/mainline/db/migrations/0066_disposition.sql`.

<a id="clause"></a>
### clause

One numbered rule inside a procedure or a standard. "Compressor high-pressure alarm setpoint
shall be 135 barg" is a clause. A clause is the unit that gets changed, and therefore the
unit that gets its history asked about.

Table `mainline.clause`, created by `verticals/mainline/db/migrations/0028_clause.sql`.

<a id="blame"></a>
### blame

Also called a **blame edge**. A pointer from a [clause](#clause) to the event that caused it
to be written, with the quoted evidence digested to a hash so the quote cannot be edited
later without the hash disagreeing.

The everyday comparison is exact: this is `git blame`, for a safety rule. You ask a line of a
procedure who wrote it and why, and you get an answer with a citation.

Table `mainline.blame_edge`, created by `verticals/mainline/db/migrations/0037_blame_edge.sql`.
Route `GET /v1/clauses/{id}/ancestry`.

<a id="ancestry"></a>
### ancestry

The chain of earlier versions and earlier incidents a [clause](#clause) descends from.

The important word is *walked*. Ancestry is computed by following [blame](#blame) edges as a
graph, at the time the question is asked. It is not a text field somebody filled in, so it
cannot be filled in wrongly, and it cannot go stale in the way a copied summary goes stale.

<a id="projection"></a>
### projection

A value the database writes onto a row **by itself**, derived from other rows, overwriting
whatever the writer supplied.

This is the load-bearing trick of the whole design. `mainline.permit.open_blocking` — the
count of unsettled [obligations](#obligation) on a permit — is a projection. An application
that sets it to zero to get its write through does not get its write through: the trigger
recomputes it from the [obligation](#obligation) rows and puts the true value back before
the constraint is evaluated.

<a id="gate"></a>
### gate

The set of database objects that refuse the [issue](#merge) write. Three of them, and they
are independent:

* a `CHECK` constraint — `gate_closed_when_issued`,
  `verticals/mainline/db/migrations/0050_permit.sql:114`
* a trigger — `permit_merge_gate`,
  `verticals/mainline/db/migrations/0130_trg_permit_merge_gate.sql:38`
* a procedure — `mainline.fn_permit_merge_gate()`,
  `verticals/mainline/db/migrations/0115_fn_permit_merge_gate.sql:44`

"Gate" never means a screen, a form step, or an approval workflow on this page. It means
those three objects.

<a id="epoch"></a>
### epoch

Written `gate_epoch`. A counter on the permit that goes up every time a new
[obligation](#obligation) arrives.

A completed [issue](#merge) points at one exact value of that counter. So an obligation that
turns up after a permit is finished cannot be quietly attached to it — the finished permit is
pinned to the epoch it was issued under, and the new obligation belongs to a later one. See
[epoch pin](#pin) for the mechanism that makes this a database error rather than a policy.

<a id="sqlstate"></a>
### SQLSTATE

The five-character code the database returns to say what it did. Four of them carry the whole
story in this document:

| Code | Meaning here |
|---|---|
| `00000` | accepted |
| `23514` | a `CHECK` constraint refused it |
| `P0001` | a procedure refused it |
| `40001` | undecided under concurrency — ask again |

A refusal that arrives as `23514` names the constraint that produced it, which is why the
constraint name is treated as the exhibit rather than the message text.

<a id="diachronic"></a>
### diachronic

Paired with **synchronic**, and the pair is the shortest statement of what is different here.

* **Synchronic** — judged on how the world **is now**. Are the isolations in place, is the
  gas test current, is the training valid.
* **Diachronic** — judged on **how it got here**. Why does this rule say 135, and who paid
  for that number.

Every permit-to-work system that ships today is synchronic. This one is diachronic.

<a id="defeater"></a>
### defeater

A recorded reason why a past incident does **not** apply to this job — for example, the
equipment involved was replaced with a different design in 2019.

The constraint that makes this honest: a defeater must itself be evidence, not an opinion. "I
judged it not relevant" is not a defeater. A pointer to the replacement record is.

<a id="mus"></a>
### MUS

Minimal unsatisfiable subset. The shortest set of facts that together force the refusal —
drop any one of them and the write would have gone through.

Plainly: not "denied", but "these three specific things, and no fewer, are why".

<a id="naa"></a>
### NAA

Nearest admissible alternative. The closest version of the request the database *would* have
accepted, where that can be computed.

Where it cannot be computed, the answer is `null` with a reason attached, never a guess. A
guessed alternative in this position would be worse than none, because a person would act on
it.

<a id="canonicalisation"></a>
### canonicalisation

Writing a data structure in one fixed byte-for-byte form, so that two machines that hash it
independently get the same answer. Key order, number formatting and whitespace all become
determined rather than incidental.

The standard used is RFC 8785 (JSON Canonicalization Scheme). Package
`packages/trappoint-jcs/`.

<a id="silence"></a>
### silence

The **silence receipt** is the record of what a search *declined* to show, with its
arithmetic — the corpus it searched over, the threshold it applied, how many candidates fell
below it.

The point: "nothing relevant was found" becomes a checkable claim instead of an absence. A
system that only reports what it surfaced can hide a miss simply by not mentioning it.

Route `GET /v1/permits/{id}/silence`. Read the scope note in
[`05-what-is-not-built.md`](05-what-is-not-built.md) before drawing a conclusion from a
receipt whose count is zero.

<a id="trappoint"></a>
### TRAPPOINT

The substrate: a specification, deterministic SQL templates, and a conformance suite.
Apache-2.0. It knows nothing about safety permits — the words "permit" and "incident" are the
[vertical](#vertical)'s, not TRAPPOINT's.

`spec/TRAPPOINT-SPEC.md`, `spec/invariants/I01…I16`, `packages/trappoint-*`.

<a id="vertical"></a>
### vertical

A product built on that substrate. MAINLINE is one, at `verticals/mainline/`.
`trappoint_ref` is the deliberately minimal reference one, at
`packages/trappoint-sql/refvertical/`.

The separation is the claim that the mechanism generalises. It is also a licence boundary:
the substrate is Apache-2.0 and forkable, the vertical is not.

<a id="conformance"></a>
### conformance

The **conformance suite** is the machine-readable case list whose passing is the **only**
meaning of "TRAPPOINT-compliant". Not a document, not a self-assessment: a list of cases and
their results.

`packages/trappoint-conformance/cases/`, manifest at `spec/conformance/manifest.toml`. Its
current census is nowhere near a passing suite and
[`05-what-is-not-built.md`](05-what-is-not-built.md) gives the numbers.

<a id="custody"></a>
### custody

The separate machinery for proving that recorded evidence has not been altered since it was
recorded — hashes, Merkle trees, cosignatures, external timestamps.

Custody is orthogonal to the [gate](#gate). The gate decides whether a write is allowed;
custody decides whether you can still believe a record from last year. Current state: **9
passed, 0 failed, 7 not checked, of 16**
[src: qa/test-state.json#external_checks.custody_bundle_verification.counts].

<a id="drift"></a>
### drift

**Projection drift** is the [projected](#projection) value disagreeing with what the base rows
actually say — the stored count says zero, the obligation rows say one.

The gate treats drift as an attack, not as a rounding error. The completing transition
re-derives the count for itself and refuses with `P0001` when the derivation disagrees with
the stored value, rather than repairing it and continuing.

<a id="refusal-depth"></a>
### refusal depth

How many independent mechanisms would each, on their own, have refused the same illegal
write.

Depth is measured by removing them one at a time and confirming the write still fails —
`packages/trappoint-conformance/unweld/`, documented at
`packages/trappoint-conformance/REFUSAL_DEPTH.md`. Redundancy that has never been tested by
removal is an assumption, not a depth.

<a id="pin"></a>
### pin

The **epoch pin**: a composite foreign key on `(subject_id, gate_epoch)` with
`ON UPDATE RESTRICT`.

What it buys, in one sentence: attaching an [obligation](#obligation) to an already-finished
permit stops being a policy violation that someone must notice, and becomes a
referential-integrity violation that the database itself refuses.
`verticals/mainline/db/migrations/0071a_epoch_pin_permit.sql`;
`verticals/mainline/db/migrations/0050_permit.sql:137`.
