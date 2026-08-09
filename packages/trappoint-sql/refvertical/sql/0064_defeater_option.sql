-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: Apache-2.0
--
-- TRAPPOINT_REF · 0064_defeater_option.sql
-- CREATE TABLE trappoint_ref.defeater_option — generated per check, so no global "N/A" exists
--
-- MI: MI11
-- I: I10
-- COUNSEL-GATED: no
-- RATIONALE: A closed vocabulary shared across every obligation degenerates into one option
--            everybody picks, and a disposition whose defeater carries no information is a
--            click-through with a signature on it. Generating the vocabulary per check
--            means the universal escape hatch would have to be written specifically for
--            this mechanism at this severity, at which point it is an authored, hashed
--            defeater rather than a default.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0064_defeater_option.sql.j2
-- @binding      packages/trappoint-sql/refvertical/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- PRIMARY KEY (check_id, defeater_code)
--   The code is unique WITHIN a check and meaningless outside it. Two obligations may
--   both offer 'PRECONDITION_ABSENT' and mean different preconditions, because the
--   prompt that gives the code its meaning is stored beside it, per check.
--
-- prompt IS THE QUESTION, NOT A LABEL
--   "Which precondition of this mechanism is absent?" is a question that can only be
--   answered wrongly in a way a reviewer can see. A label — "N/A", "not applicable" —
--   cannot be answered wrongly at all, which is exactly what makes it worthless.
--   `defeater_prompt_stated` refuses the blank string, because NOT NULL admits '' and a
--   blank prompt is a label with extra steps.
--
-- vocab_sha256 IS THE SAME VALUE ON EVERY ROW OF ONE GENERATION
--   It digests the whole option set, not the row, so a signature that pins it pins the
--   ALTERNATIVES the signer declined as well as the one they chose. A per-row digest
--   would prove the chosen option existed and prove nothing about what else was on the
--   screen — and "the only other option was 'accept'" is the interesting fact.
--
-- ON DELETE / ON UPDATE ARE LEFT AT THEIR DEFAULT, WHICH IS `NO ACTION`, DELIBERATELY.
--   A blocking check is append-only under MI01, so the cascade this foreign key would
--   need can never fire. Writing CASCADE here would be dead syntax that reads as a
--   licence to delete obligations.

CREATE TABLE trappoint_ref.defeater_option (
  check_id      UUID NOT NULL REFERENCES trappoint_ref.blocking_check (check_id),
  defeater_code STRING NOT NULL,
  prompt        STRING NOT NULL,
  vocab_sha256  BYTES NOT NULL,
  CONSTRAINT defeater_code_stated CHECK (defeater_code <> ''),
  CONSTRAINT defeater_prompt_stated CHECK (prompt <> ''),
  CONSTRAINT defeater_vocab_is_sha256 CHECK (length(vocab_sha256) = 32),
  CONSTRAINT pk_defeater_option PRIMARY KEY (check_id, defeater_code)
);
