-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0063_receipt_expiry.sql
-- CREATE TABLE mainline.receipt_expiry — the sweeper MARKS by writing a new row
--
-- MI: MI12
-- I: I09
-- COUNSEL-GATED: no
-- RATIONALE: Finding S28. exposure_receipt records what the system did, so marking one
--            expired by UPDATE would edit that record and the audit trail would show a
--            receipt that had always been expired. A separate row names the sweeper and the
--            instant, leaves the receipt untouched, and makes "who expired this and when"
--            answerable from the table rather than from a log.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0061_exposure.sql.j2
-- @binding      verticals/mainline/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- ONE ROW PER RECEIPT, EVER. `receipt_id` is both the primary key and the foreign key,
-- so a second sweep of the same receipt is 23505 rather than a second, contradictory
-- expiry record. Idempotence is a property of the schema here, not of the sweeper's
-- code — which matters because the sweeper is a scheduled job and scheduled jobs run
-- twice.
--
-- THIS TABLE DOES NOT ENFORCE EXPIRY; IT RECORDS IT. The refusal lives in
-- fn_disposition_project, which compares now() against exposure_receipt.expires_at at
-- write time and raises P0001 (case CF-21). A row here is evidence that the sweep ran,
-- and its absence never admits a signature the trigger would have refused. Two
-- mechanisms, failing differently: the sweeper can be down for an hour without the gate
-- accepting a stale receipt.
--
-- swept_by IS AN IDENTITY, NOT A BOOLEAN. "Expired automatically" and "expired by a
-- named operator running the sweeper by hand" are different facts about the same
-- receipt, and only one of them is interesting in a deposition.

CREATE TABLE mainline.receipt_expiry (
  receipt_id UUID NOT NULL REFERENCES mainline.exposure_receipt (receipt_id),
  swept_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  swept_by   STRING NOT NULL,
  CONSTRAINT expiry_swept_by_stated CHECK (swept_by <> ''),
  CONSTRAINT pk_receipt_expiry PRIMARY KEY (receipt_id)
);
