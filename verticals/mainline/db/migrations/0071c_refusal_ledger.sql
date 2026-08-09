-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0071c_refusal_ledger.sql
-- CREATE TABLE mainline.refusal_ledger — one row per refusal, constraint name verbatim
--
-- MI: MI01, MI02
-- I: I14, I01, I15
-- COUNSEL-GATED: no
-- RATIONALE: Every refusal emits an irreducible reason set, and the record of it is the
--            exhibit. The constraint name is stored verbatim because prettifying it
--            destroys the evidence; the wire payload is stored beside it and a CHECK
--            refuses any row whose columns and payload disagree, so the queryable form and
--            the evidentiary form cannot drift. There is no foreign key to the subject: the
--            commonest refusal is one that leaves no subject row behind, and a refusal that
--            cannot be recorded is the one an operator most needs.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0071c_refusal_ledger.sql.j2
-- @binding      verticals/mainline/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- COLUMN NOTES, in the order a reviewer meets them.
--
-- `sqlstate` is constrained to the four REFUSE-class codes. 40001 is excluded on purpose:
-- an undecided transaction has no reason set, so a retry that ran out of budget is a
-- different condition and must not be recorded as a refusal. 42501 is excluded because a
-- DENY is a fact about the writer, not a diagnosis of the subject.
--
-- `constraint_name` is the exhibit. `constraint_source` says how it was obtained:
-- `reported` from the driver's diagnostics, `parsed` recovered from the message text.
-- P0001 carries no constraint name in diag, so a P0001 exhibit is always `parsed` and a
-- consumer must render it as a WEAKENED diagnosis. Storing the distinction is what makes
-- a run whose exhibits were inferred distinguishable from a run whose exhibits were
-- reported.
--
-- `diagnosis` and `probe_calls` carry the honesty rule of I14 into the schema:
-- a declarative decomposition consumes no oracle calls, so `diagnosis = 'declarative'`
-- with a non-zero probe count is a row that claims two incompatible things and is refused.
--
-- `naa_kind` XOR `naa_reason`. An absent alternative without a reason is an unexplained
-- silence, and an alternative WITH a reason asserts a thing and its absence at once. The
-- XOR is the wire schema's `naa`/`naa_reason` conditional, restated where it cannot be
-- skipped.
--
-- `diagnosis = 'none'` cannot assert an alternative: an emitter that could not establish
-- minimality has no basis for a minimum-cardinality claim.
--
-- `mus_cardinality` is a stored count and `refusal_mus_agrees` compares it with the
-- payload. It exists so that "was this refusal irreducible to one fact?" is an indexed
-- integer comparison rather than a JSON traversal over a table that only grows.
--
-- ONE HONEST LIMIT, stated where a reviewer meets it. `jsonb_array_length()` raises
-- 22023 if `mus` is not an array, and 22023 is outside the refusal taxonomy. The BEFORE
-- ROW trigger at 0133 pre-empts that with a P0001 naming the problem, and BEFORE ROW
-- triggers are MEASURED to fire ahead of CHECK constraints on CockroachDB v26.2.5
-- (2026-08-09). So this CHECK has refusal depth 1, not 2: with the trigger disabled — the
-- unwelding harness does exactly that — a malformed payload produces 22023 rather than a
-- modelled code. That is a property of this one constraint and it is written here rather
-- than discovered, because the alternative expression (a type test AND-ed in front) would
-- depend on evaluation order that no dialect guarantees, which is a worse kind of not-true.

CREATE TABLE mainline.refusal_ledger (
  refusal_id        UUID NOT NULL DEFAULT gen_random_uuid(),
  observed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  spec_version      STRING NOT NULL,
  profile           STRING NULL,
  sqlstate          STRING NOT NULL,
  constraint_name   STRING NOT NULL,
  constraint_source STRING NOT NULL DEFAULT 'reported',
  message           STRING NOT NULL,
  subject_kind      STRING NOT NULL,
  subject_id        UUID NOT NULL,
  gate_epoch        INT8 NOT NULL,
  diagnosis         STRING NOT NULL,
  probe_calls       INT8 NOT NULL DEFAULT 0,
  mus_cardinality   INT8 NOT NULL,
  naa_kind          STRING NULL,
  naa_reason        STRING NULL,
  payload           JSONB NOT NULL,
  recorded_by       STRING NOT NULL,
  CONSTRAINT refusal_sqlstate_modelled
    CHECK (sqlstate IN ('23514', '23503', '23505', 'P0001')),
  CONSTRAINT refusal_constraint_not_blank CHECK (constraint_name <> ''),
  CONSTRAINT refusal_message_not_blank CHECK (message <> ''),
  CONSTRAINT refusal_spec_version_not_blank CHECK (spec_version <> ''),
  CONSTRAINT refusal_recorded_by_not_blank CHECK (recorded_by <> ''),
  CONSTRAINT refusal_profile_not_blank CHECK (profile IS NULL OR profile <> ''),
  CONSTRAINT refusal_source_modelled CHECK (constraint_source IN ('reported', 'parsed')),
  CONSTRAINT refusal_subject_kind_modelled
    CHECK (subject_kind IN ('permit', 'change_request')),
  CONSTRAINT refusal_epoch_nonneg CHECK (gate_epoch >= 0),
  CONSTRAINT refusal_diagnosis_modelled
    CHECK (diagnosis IN ('declarative', 'quickxplain', 'none')),
  CONSTRAINT refusal_probe_calls_nonneg CHECK (probe_calls >= 0),
  CONSTRAINT refusal_declarative_costs_no_probe
    CHECK (diagnosis <> 'declarative' OR probe_calls = 0),
  CONSTRAINT refusal_mus_nonempty CHECK (mus_cardinality >= 1),
  CONSTRAINT refusal_alternative_explained
    CHECK ((naa_kind IS NULL) <> (naa_reason IS NULL)),
  CONSTRAINT refusal_naa_kind_modelled
    CHECK (naa_kind IS NULL OR naa_kind IN ('dispose_obligations', 'substitute_kind',
                                            'supply_evidence', 'materialise_authority',
                                            'fork_subject')),
  CONSTRAINT refusal_naa_reason_modelled
    CHECK (naa_reason IS NULL OR naa_reason IN ('probe_budget_exhausted',
                                                'no_legal_verdict_exists',
                                                'requires_human_authority',
                                                'not_computable')),
  CONSTRAINT refusal_none_asserts_no_alternative
    CHECK (diagnosis <> 'none' OR naa_kind IS NULL),
  CONSTRAINT refusal_payload_is_object CHECK (jsonb_typeof(payload) = 'object'),
  CONSTRAINT refusal_payload_names_the_exhibit
    CHECK (payload->>'constraint' = constraint_name),
  CONSTRAINT refusal_payload_names_the_code CHECK (payload->>'sqlstate' = sqlstate),
  CONSTRAINT refusal_payload_names_the_subject
    CHECK (payload->>'subject_id' = subject_id::STRING
       AND payload->>'subject_kind' = subject_kind),
  CONSTRAINT refusal_payload_names_the_diagnosis
    CHECK (payload->>'diagnosis' = diagnosis),
  CONSTRAINT refusal_payload_names_the_alternative
    CHECK (coalesce(payload->'naa'->>'kind', '') = coalesce(naa_kind, '')),
  CONSTRAINT refusal_payload_names_the_silence
    CHECK (coalesce(payload->>'naa_reason', '') = coalesce(naa_reason, '')),
  CONSTRAINT refusal_payload_is_a_gate_outcome CHECK (payload->>'class' = 'gate'),
  CONSTRAINT refusal_p0001_exhibit_is_parsed
    CHECK (sqlstate <> 'P0001' OR constraint_source = 'parsed'),
  CONSTRAINT refusal_mus_agrees
    CHECK (jsonb_array_length(payload->'mus') = mus_cardinality),
  CONSTRAINT refusal_no_person_metric
    CHECK (payload::STRING !~ '"(score|scores|rating|ratings|threshold|thresholds|percentile|ranking|rank_score|risk_score|trustworthiness|reliability|attentiveness|competence_score)" *:'),
  CONSTRAINT pk_refusal_ledger PRIMARY KEY (refusal_id)
);
