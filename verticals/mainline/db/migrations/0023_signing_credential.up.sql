-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI01, MI27
-- I: I09
-- COUNSEL-GATED: no
-- RATIONALE: A signature is only independently checkable if the public key that verifies it is published at enrolment and kept forever, so the credential table is append-only and revocation is a column rather than a DELETE — a 2029 signature must still verify in 2036.
--
-- migration:  0023_signing_credential
-- band:       0001-0023 · dm-foundation
-- statements: 1
-- source:     ARCHITECTURE.md §5.1 (verbatim; constraints named per DM-10, index inline per DM-6)
--             · §11.4 (what a signature actually is)
-- requires:   0002 CREATE SCHEMA mainline · logically 0022 mainline.person (no FK — see 0022)
-- seeds:      none.
-- sqlstate:   23514 on attachment_closed; 23505 on the primary key (a credential id is unique)
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ENROLLED, APPEND-ONLY, LEDGER-ANCHORED. `public_key_cose` is published in the custody ledger at
-- enrolment. That is the whole trick: it means a third party can verify a human's signature
-- without us, which makes the human signature as independently checkable as the log signature.
-- `trappoint-verify` check 12 does exactly that, and it is the difference between a signature and
-- a screenshot of one.
--
-- REVOKING A CREDENTIAL NEVER INVALIDATES HISTORY. `revoked_at` is a column, not a DELETE, and the
-- old public key stays in the ledger forever. A key that is revoked in 2031 still verifies the
-- disposition it signed in 2029, because the question a court asks is "was this signed by that
-- key at that time", not "is that key still current".
--
-- `last_sign_count` REGRESSION IS AN ALARM, NOT A REFUSAL. WebAuthn's signature counter can go
-- backwards on a cloned authenticator — and also on a perfectly honest one that was restored from
-- backup, or that never implemented the counter. Refusing a safety sign-off at a workface on a
-- counter anomaly is an availability failure at the exact moment availability is the safety
-- property. So the column is maintained, the regression is written to the record loudly, and the
-- signature is accepted. The alarm is the control; the refusal would be the incident.
--
-- `attachment` IS THE SHARED-TABLET CONSTRAINT. A platform passkey on a shared crew tablet is an
-- identity belonging to the DEVICE, and every person who uses that tablet inherits it — which
-- makes non-repudiation a fiction while looking like compliance. Shared devices are permitted in
-- kiosk mode with a ROAMING ('cross-platform') authenticator only, and enrolment refuses the
-- platform variant on a shared device. The CHECK here closes the type; the device policy is
-- enforced at enrolment because the database cannot know what a tablet is.
--
-- `enrolment_assurance` CARRIES NO CHECK HERE, unlike `person.enrolment_assurance`. That is
-- deliberate and it is the more honest shape: this column records the assertion the customer's
-- enrolment flow made about THIS credential, and closing the set would silently coerce an
-- assurance vocabulary we did not author into three buckets we did. `person` is our mirror of
-- their HR record and is ours to type; this is their claim about a key and is theirs to state.
--
-- INDEX DECLARED INLINE (DM-6): one statement per file survives without an index-file explosion,
-- and the index exists from row zero. It is PARTIAL — `WHERE revoked_at IS NULL` — because every
-- hot read is "which live credentials does this signer have"; the revoked ones are read only by
-- the verifier, which comes in by credential_id and uses the primary index.

CREATE TABLE mainline.signing_credential (        -- enrolled, append-only, ledger-anchored
  credential_id       BYTES       NOT NULL,       -- the WebAuthn credential id
  signer_sub          STRING      NOT NULL,
  public_key_cose     BYTES       NOT NULL,       -- published in the ledger at enrolment
  aaguid              BYTES       NOT NULL,
  transports          STRING[]    NOT NULL,
  attachment          STRING      NOT NULL,
  enrolled_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  enrolment_assurance STRING      NOT NULL,       -- THEIR assertion, recorded as theirs
  last_sign_count     INT8        NOT NULL DEFAULT 0,
  revoked_at          TIMESTAMPTZ NULL,
  revoke_reason       STRING      NULL,
  CONSTRAINT signing_credential_pk PRIMARY KEY (credential_id),
  CONSTRAINT attachment_closed CHECK (attachment IN ('cross-platform', 'platform')),
  CONSTRAINT signer_sub_stated CHECK (signer_sub <> ''),
  CONSTRAINT last_sign_count_non_negative CHECK (last_sign_count >= 0),
  INDEX by_signer (signer_sub) WHERE revoked_at IS NULL
);
