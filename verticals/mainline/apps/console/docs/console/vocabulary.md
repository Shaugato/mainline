<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# The console's vocabulary

**A spec the build consumes.** Every table below is rendered from
`src/design/glossary.ts` by `src/design/glossary.doc.ts`, and
`tests/unit/design/glossary.test.ts` fails if this document and that code disagree by one
character. Editing a table here does not change the console; it turns CI red. Change the
data, run the test, paste what it prints.

This is ruling **R7** of `docs/leads/two-audience-ux-plan.md`, written down. The ruling is
the authority for every sentence in the first two tables and those sentences are copied
verbatim.

## What this document is for

The lead counted the terms a first-time reader meets on the shipped screens *before
anything defines them*: **twenty-one** (plan §0.4). *projection*, *canonicalisation*,
*inclusion proof*, *gate epoch*, *defeater*, *minimal unsatisfiable subset*, *corpus root*,
*clock skew* — none of them is wrong, and **all twenty-one stay**. What changes is what a
reader meets *first*.

So this is an on-ramp, never a dumbing-down. Two collections, and the split between them is
the whole design:

- **Product words** are the nine words the console says in its own prose. Each carries one
  plain sentence *and the exact database thing it names*, so a reader who wants to check
  the sentence knows which table or endpoint to open. That second column is what stops the
  plain sentence becoming a claim nobody can test: *refusal* is a nice word;
  `a 23514/P0001 error` is where you go to find out whether the nice word was earned.
- **Glossed terms** are the eighteen terms that are **never replaced** and always defined
  on first use. `minimal unsatisfiable subset` stays `minimal unsatisfiable subset`; it
  gains a sentence beside it and loses nothing.

## Where the words are rendered

`src/design/primitives/Gloss.tsx` puts a gloss **beside** a verbatim value, never inside
it, and never as a `title=`, a tooltip or a hover reveal — those are states a screenshot
cannot reproduce and a keyboard cannot reach. The kernel's own string keeps the mono face,
untouched, exactly as ruling **R8** requires; the gloss is sans, dimmer, smaller, and
plainly ours.

`src/design/primitives/PlainBand.tsx` carries at most three of these sentences at the top
of a screen, with a slot for the SYNTHETIC marker (**R5**).
`src/design/primitives/Disclosure.tsx` is where the exact material goes in PLAIN — one
deliberate, permanent click away, with its children in the DOM in **both** modes so a
screenshot and a `Ctrl-F` both find them (**R6**).

## The product's own words

These are what the console says in prose.

<!-- GENERATED:product-words — rendered from src/design/glossary.ts. Do not edit by hand. -->

| Word | The one sentence | The exact thing it names |
|---|---|---|
| **permit** | A written authorisation for one specific piece of work. | `mainline.permit` |
| **obligation** | Something that must be answered before the permit is allowed to take effect. | `mainline.blocking_check` |
| **refusal** | The database declining to make the change, and printing its own named reason for it. | a 23514/P0001 error |
| **signature** | One named person recording, under their own credential, how an obligation was answered. | `mainline.disposition` |
| **ancestry** | The trail from this rule back through the earlier events and edits it came from. | `clause_blame_closure + commit_chain` |
| **custody** | Proof that a record has not been altered since it was written down. | the ledger + checkpoint |
| **silence** | Everything the search looked at and decided not to show you — and the arithmetic for why. | `/v1/permits/{id}/silence` |
| **propagation** | Where else the same lesson was applied, and where it was not. | `/v1/lessons/{id}/propagation` |
| **synthetic** | Made up for this demonstration; corresponds to no real person, site or event. | the seed's own marker |

<!-- /GENERATED:product-words -->

## Terms that stay, and gain a first-use definition

Never replaced. Always glossed the first time a screen uses one.

<!-- GENERATED:glossed-terms — rendered from src/design/glossary.ts. Do not edit by hand. -->

| Term | First-use gloss |
|---|---|
| `projection / projected counter` | A running total the database keeps in a column so a check can be instant instead of re-counting. |
| `projection drift` | When that running total stops matching what the rows actually say — by accident, or on purpose. |
| `SQLSTATE` | The five-character code the database prints to name what it refused. 23514 means a CHECK constraint was not satisfied. |
| `constraint` | A rule written into the table itself, so no query can get around it. |
| `gate epoch` | A version number for the set of obligations; it moves when they change, so an old signature cannot be reused across the change. |
| `canonicalisation` | Writing a record in one exact byte-for-byte form, so two different computers hashing it get the same answer. (RFC 8785) |
| `inclusion proof` | A short list of hashes that proves one entry really is in the log, without re-reading the log. (RFC 6962) |
| `consistency proof` | A short list of hashes that proves the log only ever grew, and no earlier entry was rewritten. |
| `corpus root` | The exact commit of the rule-book that this page's ancestry was worked out against. |
| `clock skew` | The server's clock minus this browser's. A screenshot's timestamp means nothing without it. |
| `minimal unsatisfiable subset` | The smallest set of reasons that is on its own enough to cause the refusal — take any one away and it would not refuse. |
| `nearest admissible alternative` | The smallest thing you could actually do that would make this allowed. |
| `defeater` | The named reason a person is permitted to give for an obligation. The list is fixed per obligation; there is deliberately no general "not applicable". |
| `virulence / severity` | How bad the underlying failure was, on the scale the record itself carries. |
| `provenance chip` | The little marker saying how the console came to believe the value beside it — read from a column, recomputed here, or never established. |
| `STAGED` | This value came from a fixture, not from the live database, and the badge is there so you never have to wonder. |
| `transport` | Where these bytes came from: LIVE (a database, just now) or REPLAY (a signed bundle, verified in this browser first). |
| `seal` | Whether this browser re-did the arithmetic over the signed bytes and got the same answer. |

<!-- /GENERATED:glossed-terms -->

## The SQLSTATE map

`src/design/sqlstate.ts` **classifies** a code — retry, refuse, deny, admit, or outside the
taxonomy — which is a fact about `spec/errors.md` §1. This table **glosses** it: what the
code names, which is a fact about the SQL standard's condition for that class. Neither one
paraphrases a refusal payload. D18 and R8 both say the payload carries its own words, and
the gloss goes beside them.

The set is `spec/errors.md`'s closed gate-path set plus `42501` (refused before the gate)
and `00000` (not an error). A code outside it gets **no gloss** — `Sqlstate.tsx` already
announces an unmodelled code as unmodelled, and a sentence invented beside it would be the
console claiming it understood a refusal nobody modelled.

<!-- GENERATED:sqlstates — rendered from src/design/glossary.ts. Do not edit by hand. -->

| Code the database printed | What it names |
|---|---|
| `00000` | the statement succeeded |
| `23503` | a foreign key pointed at a row that is not there |
| `23505` | a unique index already held that value |
| `23514` | a CHECK constraint written into the table was not satisfied |
| `40001` | the database could not serialise this transaction against another one, and asks for it to be retried |
| `42501` | the role was refused by the grant graph before any gate condition was evaluated |
| `P0001` | a function raised its own named refusal |

<!-- /GENERATED:sqlstates -->

## Two console-composed headings that R7 overrules

Neither is kernel vocabulary, and nothing verbatim is lost by the change.

| ships today | becomes | what survives |
|---|---|---|
| *"The weld"* | **"What the database checks before it will merge"** | the word *weld* stays as the section's subtitle in FULL DETAIL, and in the source comments |
| *"Irreducible reason set"* | **"Why it refused — the smallest set of reasons"** | `mus` in the payload is untouched, and `minimal unsatisfiable subset` is glossed beside the heading |

## The words no sentence here may contain

R7 forbids twelve, and `FORBIDDEN_WORDS` in `src/design/glossary.ts` is that list as data
so a test can run it over every string rather than over the ones somebody remembered to
check:

> seamless, powerful, robust, enterprise, revolutionary, unlock, empower, leverage,
> effortless, trust us, simply, just

Not a style preference. Each one lets a sentence describe an effect on the reader instead
of a fact about a field, and R7's test for every added sentence is: **can I point at the
field it came from?** If not, delete it.

There is exactly one lexical carve-out, and it is written down in `glossary.ts` rather than
applied by hand: in R7's own `transport` gloss, *"LIVE (a database, just now)"* uses `just`
as a time reference and not as the minimiser the ruling bans. `forbiddenWordsIn()` excludes
the phrase `just now` and nothing else, and `glossary.test.ts` asserts that carve-out fires
**exactly once** across the whole vocabulary. A second occurrence is a test failure, and
the fix is to write the sentence differently rather than to widen the exception.
