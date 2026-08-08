-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: Apache-2.0
--
-- TRAPPOINT_REF · 0029_clause_version.sql
-- CREATE TABLE trappoint_ref.clause_version — the foreign-key target the closure needs
--
-- MI: MI25
-- I: I06
-- COUNSEL-GATED: no
-- RATIONALE: HAND-WRITTEN, NOT RENDERED. The reference vertical exists so that K1 does
--            not depend on K3: the kernel's gate reads an authority source, and in a
--            real vertical that source is an ancestry table several milestones away. A
--            binding whose authority relation does not exist cannot be conformance-
--            tested at all, so the reference vertical supplies the smallest relation
--            that makes the closure's composite foreign key real.
--
-- NOT rendered from a template, and therefore carrying no rendered-by banner:
-- `trappoint render --check` leaves this file alone by design. It is domain content of
-- the reference vertical, not substrate.
--
-- Isomorphic to ARCHITECTURE.md §5.3's `clause_version` in exactly the one respect that
-- matters here: the pair (clause_uuid, commit_id) is UNIQUE and is a foreign-key target.
-- Everything else that table carries — text, digests, the control delta, the head
-- pointer — belongs to a vertical with documents in it, and inventing it here would
-- make the reference vertical a second product rather than a proof.
--
-- `commit_id` is BYTES: a content address over the canonical commit envelope, not a
-- counter. There is no sequence anywhere in this schema, because the ledger is gap-free
-- by compare-and-swap and a gap therefore MEANS tampering.

CREATE TABLE trappoint_ref.clause_version (
  clause_uuid   UUID   NOT NULL,
  commit_id     BYTES  NOT NULL,
  site_id       UUID   NOT NULL,
  control_delta trappoint_ref.control_delta NOT NULL,
  body_sha256   BYTES  NOT NULL,
  authored_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT clause_version_commit_sized CHECK (length(commit_id) = 32),
  CONSTRAINT clause_version_body_sized CHECK (length(body_sha256) = 32),
  CONSTRAINT pk_clause_version PRIMARY KEY (clause_uuid, commit_id)
);
