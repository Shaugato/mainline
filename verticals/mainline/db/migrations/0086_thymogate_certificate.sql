-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- migration:  0086_thymogate_certificate
-- domain:     recall
-- statements: 2 (CREATE TABLE, then the deferred FK from 0085 — the cycle 0085→0086 cannot be
--             expressed in one file in either order; §18 uses the same shape at 0171)
-- invariants: MI18 (an unanchored/uncertified policy may not run — this is its M5 half)
-- source:     docs/leads/recall.md D14 · BUILD_PLAN K4 (M5 THYMOGATE)
-- requires:   0085 mainline_meas.recall_policy.thymogate_certificate_id
-- sqlstate:   23514 on `verdict_matches_arithmetic` · 23503 on an unknown certificate
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
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

ALTER TABLE mainline_meas.recall_policy
  ADD CONSTRAINT fk_thymogate_certificate
  FOREIGN KEY (thymogate_certificate_id)
  REFERENCES mainline_meas.thymogate_certificate (certificate_id);
