<!--
SPDX-FileCopyrightText: 2026 MAINLINE
SPDX-License-Identifier: CC-BY-4.0
-->

# ADR 0030 — Demo beat 4 is M8 DEFEATER LEASE, and it films `P0001`

**Status:** Accepted · **Date:** 2026-08-10 · **Decider:** corpus & demo lead · **Milestone:** ⟦H⟧
**Implements:** adversarial-review findings **S3** and **S4**; `docs/leads/corpus-demo.md` ruling **D1**
**Depends on:** `spec/errors.md` §2.5, §3.1, §3.3 · ADR 0002 (platform ground truth)
**Binds:** `verticals/mainline/demo/script/SHOT-LIST.yaml`, `.../SHOT-LIST-MWS.yaml`,
`verticals/mainline/demo/REFUSAL-STRINGS.yaml`, `verticals/mainline/demo/DEMO-HONESTY.md`

## Context

The demo's fourth beat is the diachronic flip: a fact about the world changes, and **with nobody
touching the screen** an already-issued permit is forced to suspend and fork. It is the beat that
distinguishes this system from every synchronic permit gate on the market, and it is the beat a
judge will remember.

An earlier draft of the script filmed it two ways that both turned out to be wrong, and the two
errors are different species. That is why they get one ADR rather than a line in a changelog.

### Finding S3 — the beat was scripted against a mechanism with no tables

The draft filmed **M14 SHEPARD**, the mechanical citator: treatment flags as a write precondition
on an operational state transition. M14 is real design work and it is genuinely novel. It is also
**K7**, it is **specified only**, and **it has no tables in the shipped schema**. A beat scripted
against a deferred mechanism does not announce itself; it sits in the plan looking exactly like
every other beat until capture day, when somebody discovers that the thing they are supposed to
point a camera at does not exist. BUILD_PLAN.md §5.2 tags every beat to the milestone that must be
complete for it to be shootable precisely because of this class of failure, and beat 4 is the
instance that produced the rule.

### Finding S4 — the beat filmed a SQLSTATE that cannot occur

The same draft captioned the refusal **`23503`**, the epoch pin: `merge_record` takes a composite
foreign key onto `mainline.permit (permit_id, gate_epoch)` under `ON UPDATE RESTRICT`
(`0071a_epoch_pin_permit.sql`), so bumping the epoch of a subject whose transition is already
recorded is refused by referential integrity. That is a true and load-bearing property of the
schema. It is not what happens on this path.

Read `mainline.fn_check_materialised` (`0101_fn_check_materialised.sql`). On `AFTER INSERT` of a
`blocking_check` naming a permit, it selects the permit's state `FOR UPDATE`, and:

```
IF v_state = 'merged' THEN
  RAISE EXCEPTION USING ERRCODE='P0001',
    MESSAGE='MAINLINE: precursor arrived after issue — use the post-issue recall path';
END IF;
UPDATE mainline.permit SET open_blocking = open_blocking + 1, gate_epoch = gate_epoch + 1 ...
```

The `RAISE` is **before** the `UPDATE`. On an issued permit the epoch is therefore never touched,
the foreign key never evaluates, and `23503` **cannot** be observed on this path. Filming it would
have been exactly the overclaim this project punishes in others: a screenshot of a refusal that
the code cannot produce, in a video whose entire thesis is that the database refuses.

## Decision

**S3 · Beat 4 is M8 DEFEATER LEASE.**

`mechanism_absent` is not prose. It is a **lease**: a compiled predicate over the site's own
registers, a bounded window, and a stated probability that it holds throughout that window
(`0065_mechanism_predicate.sql`, whose `watch_set_nonempty`, `non_trivial` and `predicate_bounded`
constraints each close one way of writing an uncallable lease). A changefeed watches the declared
registers. When one of them falsifies the predicate, `predicate_revocation` is written
(`0065b`), the disposition it underwrote is revoked, the blocking check re-opens, and the gate
comes back — retro-blocking a live permit.

That is the identical `revoke → re-open → epoch-pin → suspend-and-fork` path M14 would have
exercised. It is in the schema **today**, it is inside the ⟦H⟧ scope, and it costs six words of
voice-over: *"He signed it away only while this stayed true."*

M14 SHEPARD moves to the honesty card's **NOT-BUILT-YET** column, named explicitly, with its
extension point written down. It is now a required element of that column: `gen_card.py` refuses
to render a card that does not name it, and `.github/workflows/claims.yml` asserts the rendered
card contains it.

**S4 · The SQLSTATE filmed in beat 4 is `P0001`, and `23503` is never filmed there.**

The on-camera string is:

```
P0001 · MAINLINE: precursor arrived after issue
```

a prefix of the verbatim message, which is recorded in `REFUSAL-STRINGS.yaml` beside the migration
file and line it lives on. Because `diag.constraint_name` is empty for `P0001` (`spec/errors.md`
§3.1), the exhibit is the fully-qualified name of the raising object,
`mainline.fn_check_materialised`, and the message is written so that name is recoverable.

**The runtime ordering is KEPT as it is.** The obvious "fix" — reorder so the foreign key fires
and the film gets its `23503` — is refused, for a reason that matters more than the shot:
reordering makes the observable SQLSTATE a race between a `CHECK` and a foreign-key evaluation.
A refusal whose code depends on evaluation order is not deterministic, and a non-deterministic
refusal is unfilmable, unassertable in conformance, and unusable as an exhibit. `RAISE`-first is
deterministic, so the beat is re-shootable and the conformance case is stable.

**The epoch pin's necessity is demonstrated in the repository, not on camera.** The unwelding
matrix removes one mechanism at a time and asserts which histories still refuse and which now
admit. That is where structural redundancy is proved. The corpus therefore **stops claiming that
the runtime exercises the structural refusals**, and the voice-over's line about the other
refusals points at the matrix rather than at a screen.

## Consequences

**Good.**

- The beat is shootable from K5 plus the K6 changefeed, both inside ⟦H⟧ scope, so it is no longer
  a scheduling landmine.
- The filmed SQLSTATE is one a viewer can reproduce: Tier 2 of `demo/VERIFY.md` walks a stranger
  to the same message on their own laptop.
- `P0001 · MAINLINE: precursor arrived after issue` reads to a non-specialist. `23503` does not.
  The beat gained clarity by losing the code that sounded more impressive.
- Refusal depth remains ≥ 2 and is now *proved* where proof belongs — in a matrix a reader can
  run — rather than asserted over footage.

**Costs, stated.**

- The epoch pin, which is one of the more elegant things in the schema, never appears on screen.
  It is named in `REFUSAL-STRINGS.yaml` with `on_camera: false` and the reason attached, so the
  omission is a recorded decision rather than an oversight.
- Beat 4 depends on a live changefeed. `SHOT-LIST.yaml`'s fallback for the register shot is to
  write the register row directly and state the measured latency on screen; if the M8 mechanism
  itself is incomplete, the whole beat is cut and `SHOT-LIST-MWS.yaml` takes over. **Substituting
  M14 is forbidden**, and that prohibition is written into the shot list's own fallback text.

## Alternatives rejected

| Alternative | Why not |
|---|---|
| Film M14 SHEPARD anyway, with a caption saying "specification" | A caption is not a defence. The frame shows a mechanism working; a viewer remembers the frame. |
| Reorder the trigger so `23503` fires | Makes the observable code a race. Trades determinism — the property the whole product sells — for a better-sounding number. |
| Film both `P0001` and `23503` | The second one cannot be produced without staging a different history, and staging a history to obtain a SQLSTATE is fabricating an exhibit. |
| Drop beat 4 entirely | The diachronic flip is the single most differentiating thirty seconds available. It is dropped only in the MWS cut, and dropped whole. |
| Assert the epoch pin from runtime behaviour in the conformance suite | It is asserted, but by the unwelding matrix, which removes the earlier `RAISE` first. Asserting it from the *unmodified* runtime would be asserting something that never happens. |

## How this decision is enforced rather than remembered

- `REFUSAL-STRINGS.yaml` carries `R6-PRECURSOR-AFTER-ISSUE` with `on_camera: true` and
  `R7-EPOCH-PIN` with `on_camera: false` and its `why_not_filmed` text.
- `SHOT-LIST.yaml`'s beat-4 rows name the M8 refusal id and no other, and their `fallback` text
  names the M14 substitution as forbidden.
- `gen_card.py` refuses to render an honesty card whose NOT-BUILT-YET column omits M14 SHEPARD,
  and `claims.yml` asserts the rendered card names it.
- `scripts/demo/claim_hygiene.py` fails the build on a bare invariant number or a commit-SHA
  literal anywhere on the published surface, so the beat's captions cannot drift into citing a
  number instead of a name.
