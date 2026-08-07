-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- migration:  0138_trg_cue_prefix_project
-- domain:     recall
-- statements: 2 — DELIBERATE, AND THE ONLY HONEST SHAPE. Two vector sidecars, one mechanism.
--             A migration that welds the projection onto `event_cue_embedding` but not onto
--             `event_cue_coarse` leaves the sweep's blocking column forgeable in every
--             environment where the two files land apart. The pair is atomic or it is a hole.
--             (Only one migration number is reserved for this weld; splitting it would require
--             a number this domain does not own.)
-- invariants: MI25 (the projection principle on the index partition)
-- proposes:   MI31 (see 0041, 0114)
-- source:     docs/leads/recall.md D1 · ARCHITECTURE.md §5.4, §5.11
-- requires:   0114 mainline.fn_cue_prefix_project + mainline.fn_cue_coarse_project
--             · 0041 event_cue_embedding · 0042 event_cue_coarse
-- sqlstate:   P0001
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- BEFORE INSERT, because the point is to REWRITE the row rather than to refuse it. A forged
-- prefix is not an attack the writer necessarily knows it is making — the common case is a
-- stale taxonomy version or a retried batch — and refusing the insert would leave the cue
-- unembedded, which is the same unreachability by a different route. The row lands; it lands in
-- the tree its parent cue names.
--
-- There is no UPDATE trigger and there is no need for one: `event_cue_embedding` and
-- `event_cue_coarse` are write-once sidecars keyed by `cue_id`, and re-embedding under a new
-- `index_gen` is a delete-and-insert through the same weld. If an UPDATE path is ever
-- introduced, this file gains a BEFORE UPDATE trigger in the same statement or the weld is
-- half-open.
--
-- TWO FUNCTIONS, ONE MECHANISM. The trigger NAMES are the mechanism's public surface — the
-- tests, the unwelding suite and `pg_get_triggerdef()`'s attestation all address them by name —
-- and they are unchanged. Which function each weld calls is an implementation detail forced by
-- the platform; 0114's PLATFORM NOTE 2 records why, and records that the reason is unverified
-- rather than pretending it is settled.

CREATE TRIGGER cue_prefix_project_embedding BEFORE INSERT ON mainline.event_cue_embedding
  FOR EACH ROW EXECUTE FUNCTION mainline.fn_cue_prefix_project();

CREATE TRIGGER cue_prefix_project_coarse BEFORE INSERT ON mainline.event_cue_coarse
  FOR EACH ROW EXECUTE FUNCTION mainline.fn_cue_coarse_project();
