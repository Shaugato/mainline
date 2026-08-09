<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# `mainline-cartographer` — the blame resolver

> Every clause of a procedure, setpoint or critical control carries a blame pointer to
> the incident that wrote it. This package is the code that follows that pointer, and
> the code that proposes one where none is recorded.

The Cartographer is agent #2 of the fleet (`ARCHITECTURE.md` §8.4): tier T1, SQL read on
`clause*`, `INSERT` on `identity_residue` and **provisional** `blame_edge`, and nothing
else. This distribution is its blame half. Its clause-identity half is the deterministic
cascade in `mainline-domain` and the `adjudication` call profile in `mainline-agentkit`;
neither is re-implemented here.

## Two halves, one pointer

| Half | Module | Model? | Driver? |
|---|---|---|---|
| Follow a pointer | `resolve.py` | no | no |
| Propose a pointer | `profile.py` + `propose.py` | one zero-tool call | no |
| Decide what survives | `verify.py` | no | no |
| Reach the database | `emit.py` | no | statements + params only |

## Following: four refusals, each one nameable

```python
resolved = resolve_blame_pointer(
    clause_uuid=clause,
    as_of_commit=commit_hex,
    closure=closure_row,  # mainline.clause_blame_current
    events=ancestor_rows,  # mainline.event
    edges=edge_rows,  # mainline.blame_edge
)
resolved.headline()  # the incident a reader is shown first
resolved.ancestry_complete  # False when the closure was truncated
```

* **`BlameClosureAbsent`** — no closure row. P3: *we do not know the ancestry* and
  *there is no ancestry* must never look alike. The message is byte-identical to the
  one `fn_check_project` raises, so one log grep finds both.
* **`AncestryUnresolvable`** — an ancestor id with no event row. A pointer we cannot
  follow is a precursor we cannot show a signer.
* **`StaleClosure`** — the projection is *below* an observed ancestor severity.
  Under-banding would let the gate demand a weaker clearance than the ancestry
  justifies. The opposite direction fails safe and is reported as `over_banded`.
* **`InferenceActivated`** — an `inferred_semantic` edge that is `active`, or that
  reached the closure. The DDL forbids the first and the Projector forbids the second;
  this is the read-side assertion that still fires if either is dropped.

`ancestry_complete` is a field, not a footnote. A truncated closure must never be
indistinguishable from a complete one.

**This package does not band.** `max_severity` and `virulence` are projections written
once, by the Projector, in the closure. They are read verbatim here. A second banding
implementation would be a second answer to a question that must have exactly one, and
from that moment the interesting question stops being *what is the ancestry* and becomes
*which of our two programs is right*.

## Proposing: what the model may see, and what it may not

The `blame_link` call profile is `effort: high`, zero-tool, JSON-Schema-constrained, and
its output model carries **no severity field, no likelihood field and no state field**.
The profile's forbidden-token guard refuses at *import time* any output property whose
name contains `severity`, `rationale`, `disposition`, `clearance`, `defeater` and the
rest — so that prohibition is checked, not remembered.

* The model never sees a clause UUID. It is shown labels `C1`, `C2`, … that we minted.
  A hallucinated `C9` is a dictionary miss; a hallucinated UUID would have been a
  plausible-looking row pointing at the wrong clause.
* The model must copy one `control_class` **verbatim from the trusted context**, which
  came from `mainline.control_failure`. This is layer 4 of the injection posture:
  an injected instruction can change field values, but it cannot conjure a failed
  barrier the ICAM record does not contain.
* Every link carries two quotes — one from the incident, one from the clause.
  `bind_quote` finds each by exact search. **Not found ⇒ dropped. Found twice ⇒
  dropped**, because a span that could be either of two places is not a span.

Failures drop the link, not the call. Every drop is returned with a reason from a closed
vocabulary, and `VerifiedBlame.arithmetic()` renders the counts for the silence ledger.
A call that proposed five links and lost all five, a call that abstained, and a call that
was refused are three distinguishable rows with three distinguishable causes.

## The one row it builds

`ProvisionalBlameEdge` **cannot be constructed** with a basis other than
`inferred_semantic` or a state other than `provisional`. `emit.insert_blame_edge` writes
both as SQL *literals* rather than parameters: a parameter is a value a caller chooses,
a literal is a value nobody chooses. The DDL constraint `inference_never_blocks` then
sits behind both as the actual enforcement.

`p_link` is carried as an integer count of thousandths derived from the model's named
confidence band, and converted to a decimal exactly once, at the wire. Nothing in this
process holds it as a float, because IEEE-754 has no stable byte form and this row is
hashed (ADR 0042).

## What it does not claim

* It does not claim an inferred link is true. It claims a reviewer should look.
* It does not fix a plausible-but-false narrative in an otherwise clean PDF. Content
  authenticity is out of scope; provenance is in scope.
* It has never been run against a live Bedrock endpoint on this build machine — AWS
  credentials are not valid here as of 2026-08-09. The cassette provider is the default
  and the tests run with no AWS account and no network.

## Tests

`tests/unit/cartographer/`. Four files: the resolver's refusals, the verifier's drops,
the inference law, and one end-to-end cassette-replayed proposal that includes a poisoned
clause whose injected "instruction" is proposed as evidence and is dropped because it
does not bind.
