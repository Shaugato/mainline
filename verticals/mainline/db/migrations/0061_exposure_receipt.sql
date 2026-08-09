-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0061_exposure_receipt.sql
-- CREATE TABLE mainline.exposure_receipt — what was actually shown, when, over what corpus
--
-- MI: MI12
-- I: I09
-- COUNSEL-GATED: no
-- RATIONALE: A signature is only worth what the signer was shown. This row records the
--            server instant, the corpus root and the silence receipt in force at the read,
--            so the record proves what the system knew at signing time — which is the
--            answer to the plaintiff line "your own system surfaces it today". It is
--            append-only: expiry is a new row in 0063, never an edit here.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0061_exposure.sql.j2
-- @binding      verticals/mainline/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- SUBJECT-POLYMORPHIC, over the 2 gated subject(s) this binding declares:
--   permit -> mainline.permit (permit_id)
--   change_request -> mainline.change_request (cr_id)
--
-- RULING D2, EXTENDED TO THIS TABLE, AND THE EXTENSION IS ARGUED RATHER THAN ASSUMED.
-- §5.5 gives this table `permit_id UUID NOT NULL`, which predates finding S16 exactly
-- as `disposition.permit_id NOT NULL` did. The consequence is mechanical: a disposition
-- must composite-FK onto an exposure line, an exposure line must belong to a receipt,
-- and a receipt that can only name a permit means a change request which trips
-- `weaken_over_blood` can never be dispositioned. MI30 — "a change_request merges only
-- with zero open blocking checks" — would then be satisfiable only by never opening one,
-- which turns the protected repository into a brick wall rather than a gate. D2's own
-- justification therefore reaches this table, and the same three constraints apply.
--
-- issued_at IS THE SERVER CLOCK (finding S7). Deliberation is derived as
-- now() - issued_at inside fn_disposition_project, so a client-supplied issue time is a
-- client-supplied deliberation measurement. There is no path by which a caller sets it.
--
-- issued_hlc IS ADVISORY ORDERING ONLY. It is a provisional hybrid-logical timestamp,
-- useful for ordering two receipts issued in the same transaction and worth nothing in
-- evidence. Nothing in the gate reads it, and no claim in this repository rests on it.
--
-- corpus_root AND silence_receipt_id ARE WHY THIS ROW DEFEATS THE HINDSIGHT ARGUMENT.
-- The first pins the custody-ledger checkpoint root at the read; the second pins the
-- arithmetic of what the recall declined to surface, with its reasons. Together they
-- make "what did the system know at 02:14" a question with a recorded answer instead of
-- a re-run of today's index against today's corpus.
--
-- silence_receipt_id CARRIES NO FOREIGN KEY. The silence ledger lives in the vertical's
-- measurement schema and is not substrate; a substrate table that referenced it could
-- not render for a binding that measures silence differently, and the object test in
-- MR-1 puts it outside. The binding is asserted by the gate transaction that writes both
-- rows, and the digest in receipt_digest covers the identifier.
--
-- ttl_bounded IS A BOUND, NOT A PRESENCE TEST (finding S12, invariant MI28). expires_at
-- being NOT NULL would admit a receipt that expired before it was issued. Comparing the
-- two columns is legal in a CHECK because both are columns; comparing either to now() is
-- not, which is why write-time expiry lives in the projection trigger.

CREATE TABLE mainline.exposure_receipt (
  receipt_id         UUID NOT NULL DEFAULT gen_random_uuid(),
  subject_kind       STRING NOT NULL,
  permit_id          UUID NULL REFERENCES mainline.permit (permit_id),
  cr_id              UUID NULL REFERENCES mainline.change_request (cr_id),
  actor_sub          STRING NOT NULL,
  issued_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  issued_hlc         DECIMAL NOT NULL,
  expires_at         TIMESTAMPTZ NOT NULL,
  corpus_root        BYTES NOT NULL,
  silence_receipt_id UUID NOT NULL,
  policy_version     STRING NOT NULL,
  total_tokens       INT8 NOT NULL,
  receipt_digest     BYTES NOT NULL,
  CONSTRAINT ttl_bounded CHECK (expires_at > issued_at),
  CONSTRAINT receipt_subject_kind_known
    CHECK (subject_kind IN ('permit', 'change_request')),
  CONSTRAINT exactly_one_subject
    CHECK ((permit_id IS NULL) <> (cr_id IS NULL)),
  CONSTRAINT subject_matches
    CHECK ((subject_kind = 'permit' AND permit_id IS NOT NULL)
        OR (subject_kind = 'change_request' AND cr_id IS NOT NULL)),
  CONSTRAINT receipt_actor_sub_stated CHECK (actor_sub <> ''),
  CONSTRAINT receipt_policy_version_stated CHECK (policy_version <> ''),
  CONSTRAINT receipt_corpus_root_is_sha256 CHECK (length(corpus_root) = 32),
  CONSTRAINT receipt_digest_is_sha256 CHECK (length(receipt_digest) = 32),
  CONSTRAINT receipt_tokens_nonneg CHECK (total_tokens >= 0),
  CONSTRAINT pk_exposure_receipt PRIMARY KEY (receipt_id)
);
