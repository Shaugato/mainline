-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: Apache-2.0
--
-- TRAPPOINT_REF · 0023_signing_credential_index.sql
-- CREATE INDEX signing_credential_by_signer — live credentials only
--
-- MI: MI27
-- I: I09
-- COUNSEL-GATED: no
-- RATIONALE: Partial on revoked_at IS NULL. The lookup the signing path performs is which
--            credentials may this person sign with NOW, and a revoked key must never be a
--            candidate; the revoked rows stay in the table forever because a 2029 signature
--            must still verify in 2036. Naming the index for its table rather than
--            by_signer keeps exhibit names unique schema-wide.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0021_identity.sql.j2
-- @binding      packages/trappoint-sql/refvertical/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.

CREATE INDEX signing_credential_by_signer
  ON trappoint_ref.signing_credential (signer_sub)
  WHERE revoked_at IS NULL;
