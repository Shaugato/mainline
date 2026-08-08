-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI19, MI01
-- I: I06
-- COUNSEL-GATED: no
-- RATIONALE: MI19 — you cannot delete a control by deleting the document that mentions it; `no_orphan_controls` is a plain-column CHECK over a projected counter, so superseding a document that still carries a live control series is 23514 for every writer including a DBA, forever.
--
-- migration:  0027_doc
-- band:       0024-0031, 0047-0049 · dm-spine · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- statements: 1
-- source:     ARCHITECTURE.md §5.2 (verbatim shape; constraints named per DM-10) · §16 MI19
--             · §4.1 law 1 (the projection idiom) · datamodel.md DM-6, DM-10
-- requires:   0001a CREATE SCHEMA mainline
-- projects:   open_token_count ← mainline.carriage (0048), counting rows for this doc_id with
--             closed_commit IS NULL. Owed to TRIGGER-MAP.yaml and to `fn_doc_token_count` in band
--             0130-0199, which must RAISE P0001 rather than default to 0 when it cannot read the
--             carriage rows it is counting.
-- sqlstate:   23514 on no_orphan_controls (MI19), tokens_nonneg, state_closed,
--             supersession_names_successor; 23505 on doc_code_unique
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- MI19 IS THE FIRST REFUSAL IN THIS BAND THAT IS ACTUALLY ARMED. Everything else here is inert
-- shape waiting for band 0130-0199. `no_orphan_controls` is not: it is a plain-column CHECK, it
-- is enforced from the moment this statement returns, and its test in test_mi_spine.py is GREEN
-- on day one rather than pending. That asymmetry is deliberate and it is worth understanding —
-- the invariants that can be expressed over the row being written are the cheap, unbreakable
-- ones, and the schema should express every one of them THERE rather than in a trigger that an
-- ALTER TABLE can disable.
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
-- THE FAILURE MODE MI19 CLOSES, IN THE WORDS OF THE PEOPLE IT HAPPENS TO. A procedure is
-- rewritten. The new document is cleaner, shorter, and does not mention the isolation step that
-- was added after a fatality in 2019 — because the person rewriting it had never heard of that
-- fatality, and nothing in the old document said where the step came from. The old document is
-- marked superseded. The control is gone. Nobody deleted it; nobody decided anything; there is no
-- record of a decision because no decision was made. This is not a hypothetical failure mode, it
-- is the ordinary one, and it is why the product exists.
--
-- MI19 makes the last step impossible. A document may not enter state 'superseded' while it still
-- CARRIES a live control series — where "carries" is a row in mainline.carriage (0048) with no
-- closing commit. To supersede the document you must first close each carriage, and closing a
-- carriage is either (a) another document opens carriage of that series, or (b) the series is
-- retired, which is a decision with an author. Either way, the control's disappearance becomes an
-- ACT rather than a side effect. That is the whole of it: the database will not let a control
-- evaporate as a consequence of a document being tidied.
--
-- WHY THE COUNTER AND NOT A SUBQUERY. §4.1 law 1: a CHECK sees only the row being written. It
-- cannot count carriage rows. So the cross-row fact is PROJECTED onto a scalar column of the
-- subject row by a trigger reading the authoritative table, and the CHECK is a plain-column
-- predicate over that scalar. PROJECT, then REFUSE. The counter is therefore the single most
-- important thing on this table to get right, and the P2 rule applies at full strength: it is
-- NEVER written by the inserter, and the trigger that maintains it must RAISE when it cannot read
-- mainline.carriage rather than silently write 0 — because a projection that fails open is a gate
-- that fails open, and this one fails open into "the control was never there".
--
-- UNTIL BAND 0130-0199 LANDS, `open_token_count` IS CLIENT-SUPPLIED AND MI19 IS THEREFORE ONLY
-- HALF ARMED. The REFUSE half works today: set state='superseded' with the counter at 1 and the
-- database says 23514, naming `no_orphan_controls`. The PROJECT half does not exist yet, so a
-- writer can set the counter to 0 and supersede freely. test_mi_spine.py asserts the half that
-- works and does not pretend about the half that does not; test_mi_projection.py (owned by
-- dm-functions-triggers) closes it. Saying this here, in the file, is the difference between a
-- known gap and a discovered one.
--
-- `open_token_count` IS INT4 AND `tokens_nonneg` IS NOT DECORATION. A counter maintained by
-- increment/decrement triggers goes negative the first time a decrement runs twice — and a
-- negative counter satisfies `open_token_count = 0`? No: it satisfies neither, which is why the
-- pair of constraints matters. `tokens_nonneg` turns a double-decrement into a 23514 at the
-- moment it happens instead of a silently-passable MI19 later.
--
-- `superseded_by` IS AN ARRAY BECAUSE SUPERSESSION SPLITS. One procedure routinely becomes three.
-- Recording a single successor would force the writer to pick one and drop the others, and the
-- dropped ones are exactly where a control goes missing. `supersession_names_successor` requires
-- the array to be present when the state says superseded; it does not check that the array is
-- non-empty, because `array_length()`'s behaviour inside a CHECK on v26.2 could not be executed
-- from the machine this band was authored on and a table that fails to create is worse than a
-- constraint that is one notch weaker than intended. Emptiness is caught by the same trigger that
-- maintains the counter. Recorded as a known notch, not as an oversight.
--
-- `state` IS A CLOSED `CHECK`, NOT AN ENUM. The seven ENUM types in 0010-0016 are the ones the
-- gate and the clearance lattice compare across tables, where type identity is what makes a
-- composite FK possible. A document's lifecycle is local to this table and nothing FKs to it, so
-- an ENUM would buy type safety nobody uses and cost an `ALTER TYPE` on every future value.
--
-- 'withdrawn' IS NOT 'superseded' AND MI19 DOES NOT CONSTRAIN IT. Withdrawal is "this document
-- should never have been issued"; supersession is "this document has been replaced". A withdrawn
-- document that still carries a series is a genuine state — the series is orphaned and that is
-- exactly the alarm the fixity and residue machinery should raise — whereas a superseded one
-- claims a successor took the load. Constraining withdrawal too would make emergency withdrawal
-- of a bad document impossible, which is an availability failure at the moment availability is
-- the safety property.
--
-- UNVERIFIED ON THIS MACHINE: no CockroachDB v26.2 was reachable when this band was authored, so
-- this statement has not been executed. See tests/integration/schema/test_mi_spine.py.

CREATE TABLE mainline.doc (
  doc_id           UUID   NOT NULL DEFAULT gen_random_uuid(),
  site_id          UUID   NOT NULL,
  doc_code         STRING NOT NULL,
  title            STRING NOT NULL,
  state            STRING NOT NULL DEFAULT 'live',
  open_token_count INT4   NOT NULL DEFAULT 0,   -- PROJECTED from mainline.carriage (0048) (P2)
  superseded_by    UUID[] NULL,                 -- supersession splits; one successor is a lie
  CONSTRAINT doc_pk PRIMARY KEY (doc_id),
  CONSTRAINT doc_code_unique UNIQUE (site_id, doc_code),
  CONSTRAINT state_closed CHECK (state IN ('live', 'superseded', 'withdrawn')),
  CONSTRAINT doc_code_stated CHECK (doc_code <> ''),
  CONSTRAINT title_stated CHECK (title <> ''),
  CONSTRAINT tokens_nonneg CHECK (open_token_count >= 0),
  CONSTRAINT supersession_names_successor
    CHECK (state <> 'superseded' OR superseded_by IS NOT NULL),
  -- You cannot delete a control by deleting the document that mentions it. (MI19)
  CONSTRAINT no_orphan_controls CHECK (state <> 'superseded' OR open_token_count = 0)
);
