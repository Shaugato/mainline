-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI18
-- I: I08
-- COUNSEL-GATED: no
-- RATIONALE: A retrieval system that has only ever been measured on what it SHOULD return has not been measured on what it MUST NOT return, so negative selection is an evaluation with its own artefact; and `verdict_matches_arithmetic` makes the verdict not an opinion about the count but the count itself, for every writer including the harness that wrote it.
--
-- migration:  0086_thymogate_certificate
-- band:       0080-0089z · recall · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- domain:     recall
-- statements: 1
-- source:     docs/leads/recall.md D14 · BUILD_PLAN K4 (M5 THYMOGATE)
-- requires:   0002 CREATE SCHEMA mainline_meas
-- companion:  0086a_recall_policy_thymogate_fk.sql — the other half of the 0085→0086 cycle.
--             See THE DEFERRED CYCLE below; this file must land first.
-- sqlstate:   23514 on `verdict_matches_arithmetic` / `panel_non_empty` / `missed_within_panel`
-- forward-only; no .down.sql exists at or below the protected floor (DM-14). Under MR-5 there
--             is no .up.sql either: the suffix named a counterpart that is illegal by
--             construction.
--
-- M5 THYMOGATE — NEGATIVE SELECTION. The immune-system analogy is exact and it is the reason
-- this table exists at all: a retrieval system that has only ever been measured on what it
-- SHOULD return has not been measured on what it MUST NOT return. The panel is a fixed set of
-- permits and events that are superficially similar and genuinely unrelated — same asset class,
-- same vocabulary, different mechanism — and a policy passes only if it recalls none of them.
--
-- The certificate is emitted by a HARNESS run, not by the retriever, because a retriever that
-- certifies itself certifies nothing (D14).
--
-- `config_digest` binds the certificate to the exact policy configuration measured; a
-- certificate whose digest does not match the policy it is attached to is a stale certificate
-- and the K8 promotion check refuses it.
--
-- `verdict_matches_arithmetic` is a REFUSE in the TRAPPOINT sense: the verdict is not an
-- opinion about the count, it IS the count. A certificate cannot say 'pass' while recording
-- misses, for any writer, including the harness that wrote it.
--
-- ── THE DEFERRED CYCLE, AND WHY IT IS NOW TWO FILES ──────────────────────────────────────────
-- `mainline_meas.recall_policy` (0080, extended by 0085) carries `thymogate_certificate_id`, and
-- this table's PK is what that column references — a cycle across two tables that cannot be
-- expressed in one file in either order. §18 already uses this shape at 0171: create both
-- tables, then add the FK as its own statement afterwards.
--
-- The FK used to be the second statement of THIS file. It is now `0086a`, because the runner
-- does not wrap a migration body in a transaction — CockroachDB DDL is not transactional across
-- statements — so a two-statement file that fails on its second leaves the schema half-applied
-- with the version unrecorded, and `dirty` names a FILE rather than a STATEMENT. Splitting is
-- also what makes the cycle legible: the whole point of the deferred-FK shape is that the two
-- halves are ordered and separable, and writing them into one file hid the very structure that
-- justifies them. `0086a` is a band-overflow suffix inside recall's own `0080`-`0089z` grant
-- (MR-5), not a borrowed number.

CREATE TABLE mainline_meas.thymogate_certificate (
  certificate_id UUID   NOT NULL DEFAULT gen_random_uuid(),
  config_digest  BYTES  NOT NULL,               -- sha256 over the JCS of the measured config
  panel_digest   BYTES  NOT NULL,               -- sha256 over the JCS of the panel itself
  panel_size     INT4   NOT NULL,
  n_missed       INT4   NOT NULL,               -- panel members the policy WOULD have recalled
  verdict        STRING NOT NULL CHECK (verdict IN ('pass','fail')),
  issued_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT thymogate_certificate_pk PRIMARY KEY (certificate_id),
  CONSTRAINT panel_non_empty CHECK (panel_size >= 1),
  CONSTRAINT missed_within_panel CHECK (n_missed >= 0 AND n_missed <= panel_size),
  CONSTRAINT verdict_matches_arithmetic CHECK ((verdict = 'pass') = (n_missed = 0))
);
