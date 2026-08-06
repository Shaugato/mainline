-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- PREREQUISITE FIXTURE — A STAND-IN FOR ANOTHER WORKER'S MECHANISM.
--
-- `mainline.fn_refuse_mutation` and its ~30 triggers are ARCHITECTURE.md §5.11 #9 and belong to
-- the trigger band (0130-0199, `dm-functions-triggers`). `mainline_meas.silence_ledger`,
-- `silence_receipt` and `recall_candidate` are three of the tables on its list.
--
-- RC-07 asserts that the silence ledger is append-only. That assertion is only worth making
-- against the DEPLOYED mechanism, so the suite looks for a BEFORE UPDATE/DELETE trigger on
-- `silence_ledger` first and uses it if it is there. This file is applied ONLY when it is not —
-- so that the recall band can be exercised in isolation — and when it is applied the test says
-- so, loudly, in its report. A test that silently exercises its own fixture and calls the
-- result a passing invariant is worse than a missing test.
--
-- The function body is copied from §5.11 #9 so that the stand-in and the real mechanism produce
-- the identical SQLSTATE and the identical message.

CREATE FUNCTION mainline.fn_refuse_mutation() RETURNS TRIGGER LANGUAGE PLpgSQL AS $$
BEGIN
  RAISE EXCEPTION USING ERRCODE='P0001',
    MESSAGE='MAINLINE: this table is append-only; write a new row';
END $$;

CREATE TRIGGER silence_ledger_append_only
  BEFORE UPDATE OR DELETE ON mainline_meas.silence_ledger
  FOR EACH ROW EXECUTE FUNCTION mainline.fn_refuse_mutation();
