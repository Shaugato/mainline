-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: Apache-2.0
--
-- TRAPPOINT_REF · 0022_signing_credential.sql
-- CREATE TABLE trappoint_ref.signing_credential — enrolled, append-only, ledger-anchored
--
-- MI: MI27
-- I: I09
-- COUNSEL-GATED: no
-- RATIONALE: The public key is published in the custody ledger at enrolment, so
--            verification of an old signature never depends on this table still holding the
--            key, and revocation never reaches backwards. A shared crew tablet is permitted
--            only with a roaming authenticator: a platform passkey on a shared device is an
--            identity belonging to the device, and the attachment column is what lets
--            enrolment refuse it.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0021_identity.sql.j2
-- @binding      packages/trappoint-sql/refvertical/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- The partial index is NOT declared inline here. It is migration 0023, one statement
-- per file, so that a failed index build is a diagnosable version rather than a
-- half-created table.
--
-- last_sign_count is the WebAuthn signature counter. It goes up or the authenticator
-- has been cloned; the check belongs to the service that verifies an assertion, and the
-- column exists so that service has somewhere to compare against.

CREATE TABLE trappoint_ref.signing_credential (
  credential_id       BYTES NOT NULL,
  signer_sub          STRING NOT NULL,
  public_key_cose     BYTES NOT NULL,
  aaguid              BYTES NOT NULL,
  transports          STRING[] NOT NULL,
  attachment          STRING NOT NULL,
  enrolled_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  enrolment_assurance STRING NOT NULL,
  last_sign_count     INT8 NOT NULL DEFAULT 0,
  revoked_at          TIMESTAMPTZ NULL,
  revoke_reason       STRING NULL,
  CONSTRAINT credential_attachment_known
    CHECK (attachment IN ('cross-platform', 'platform')),
  CONSTRAINT credential_revocation_reasoned
    CHECK ((revoked_at IS NULL) = (revoke_reason IS NULL)),
  CONSTRAINT credential_sign_count_nonneg CHECK (last_sign_count >= 0),
  CONSTRAINT pk_signing_credential PRIMARY KEY (credential_id)
);
