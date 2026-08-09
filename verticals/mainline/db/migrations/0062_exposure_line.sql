-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0062_exposure_line.sql
-- CREATE TABLE mainline.exposure_line — one line per obligation actually rendered
--
-- MI: MI12
-- I: I09
-- COUNSEL-GATED: no
-- RATIONALE: The composite key (receipt_id, check_id) is the foreign-key target the
--            disposition points at, so a signature against an obligation that was never
--            rendered to that actor in that receipt is 23503 on fk_exposure rather than an
--            application-level warning. payload_digest is the digest of the exact text
--            shown, so the claim is about the bytes rendered and not about a row identifier
--            that could later be re-rendered differently.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0061_exposure.sql.j2
-- @binding      verticals/mainline/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- THE PRIMARY KEY IS THE MECHANISM. `(receipt_id, check_id)` is a UNIQUE target, and
-- `disposition.fk_exposure` references exactly those two columns in exactly that order.
-- Reordering them, or adding a column to this key, silently breaks that foreign key at
-- migration time — which is why the order is stated here rather than left to chance.
--
-- payload_digest IS THE DIGEST OF WHAT WAS RENDERED, NOT OF THE ROW. Two receipts may
-- render the same obligation with different amounts of surrounding evidence; the digests
-- differ, and the difference is the record. A digest over the check_id would be a
-- tautology that proves nothing about the exposure.
--
-- tokens FEEDS THE READING FLOOR AND NOTHING ELSE. t_min(R) = tau_0 + (sum of tokens
-- dispositioned against R) / rho. Breaching the floor does not raise: it records, it
-- projects a counter onto the subject, and it PRICES the consequence — the subject
-- cannot complete without a countersignature from a second, differently-credentialed
-- signer. Fast stays legal; it just names a second person. That is finding S19, and this
-- column is its only input.
--
-- NO FOREIGN KEY TO A "line ordinal". Lines are identified by the obligation they
-- render, not by their position on a screen: an ordinal would make the same exposure
-- into two different receipts depending on scroll order.

CREATE TABLE mainline.exposure_line (
  receipt_id     UUID NOT NULL REFERENCES mainline.exposure_receipt (receipt_id),
  check_id       UUID NOT NULL REFERENCES mainline.blocking_check (check_id),
  payload_digest BYTES NOT NULL,
  tokens         INT8 NOT NULL,
  CONSTRAINT line_payload_digest_is_sha256 CHECK (length(payload_digest) = 32),
  CONSTRAINT line_tokens_positive CHECK (tokens > 0),
  CONSTRAINT pk_exposure_line PRIMARY KEY (receipt_id, check_id)
);
