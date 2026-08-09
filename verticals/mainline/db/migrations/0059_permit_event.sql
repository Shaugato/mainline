-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0059_permit_event.sql
-- CREATE TABLE mainline.permit_event — a chain, not a tree
--
-- MI: MI09, MI10, MI24
-- I: I04, I01
-- COUNSEL-GATED: no
-- RATIONALE: UNIQUE (subject_id, prev_seq) is a lock-free compare-and-swap: two transitions
--            extending the same head collide on 23505, so a forked history is impossible
--            even if the isolation level were downgraded, and this platform has no advisory
--            locks with which to get a lock-based head guard wrong. The legal edge set is a
--            foreign-key target rather than an if-statement, so an illegal transition is
--            23503 with a constraint name attached for every writer including the one
--            nobody anticipated. The chain digest is computed by the server over normalised
--            JSONB and its predecessor input is verified by trigger rather than trusted,
--            which is the difference between a comment claiming a chain and a chain.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0059_subject_event.sql.j2
-- @binding      verticals/mainline/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- Sequence positions are DERIVED IN-TRANSACTION and defended by the CAS below. There is
-- no generator anywhere in this schema, and that is what lets the ledger claim a gap
-- MEANS tampering: a generator allocates outside the transaction and a rolled-back
-- transaction consumes a value without producing a row, so under one a gap means
-- nothing at all.
--
-- prev_digest    the writer's declaration of what it is extending. VERIFIED against the
--                stored predecessor by mainline.fn_permit_event_chain, never trusted
--                (P0001; conformance cases CF-16 and CF-17).
-- chain_digest   COMPUTED BY THE SERVER (GT-13 PASS, measured 2026-08-08 on
--                cockroachdb/cockroach:v26.2.5). The inserter cannot choose it. It carries
--                no length CHECK because digest() is total and 32 bytes wide by
--                construction; a constraint that can never fire is noise in an exhibit
--                list. (Measured: a CHECK over a STORED generated column IS legal here —
--                the omission is a choice, not a limitation.)
-- at             a wall-clock record, never a gate input. Time cannot appear in a CHECK
--                because now() is not immutable, and nothing here pretends otherwise.

CREATE TABLE mainline.permit_event (
  permit_id     UUID   NOT NULL,
  seq           INT8   NOT NULL,
  prev_seq      INT8   NOT NULL,
  from_state    mainline.subject_state NOT NULL,
  to_state      mainline.subject_state NOT NULL,
  subject_kind  STRING NOT NULL DEFAULT 'permit',
  actor_sub     STRING NOT NULL,
  payload       JSONB  NOT NULL,
  prev_digest   BYTES  NOT NULL,
  at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  chain_digest  BYTES  AS (digest(prev_digest || payload::STRING::BYTES, 'sha256')) STORED,
  CONSTRAINT permit_event_kind_pinned CHECK (subject_kind = 'permit'),
  CONSTRAINT permit_event_seq_ordered CHECK (seq > prev_seq AND prev_seq >= 0),
  CONSTRAINT permit_event_prev_digest_sized CHECK (length(prev_digest) = 32),
  CONSTRAINT permit_event_actor_stated CHECK (actor_sub <> ''),
  CONSTRAINT fk_permit_event_subject FOREIGN KEY (permit_id)
    REFERENCES mainline.permit (permit_id)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  -- The legal edge set as QUERYABLE DATA. An illegal transition is 23503 against a row
  -- that is not there, not a branch in application code that a later commit can delete.
  CONSTRAINT legal_edge FOREIGN KEY (subject_kind, from_state, to_state)
    REFERENCES mainline.subject_transition (subject_kind, from_state, to_state)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT pk_permit_event PRIMARY KEY (permit_id, seq),
  -- THE COMPARE-AND-SWAP. A chain, not a tree.
  CONSTRAINT linear UNIQUE (permit_id, prev_seq)
);
