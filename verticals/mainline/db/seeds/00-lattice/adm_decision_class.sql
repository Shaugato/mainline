-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- seed:      00-lattice/adm_decision_class
-- table:     mainline.adm_decision_class   (migration 0020)
-- rows:      6
-- owner:     dm-foundation
-- MI:        MI01 (append-only) · the register that makes I15 auditable from outside
-- I:         I15 — allegation firewall
-- determinism: entirely natural keys and literals; no now(), no gen_random_uuid() (DM-12)
--
-- THE APP 1.7 REGISTER, live 10 December 2026. `disclosure_text` is the sentence the customer's
-- privacy policy actually carries, stored next to the decision it describes so that the two cannot
-- drift — a privacy policy paragraph and the system it describes are usually maintained by
-- different people on different cycles, and the gap between them is the finding.
--
-- READ `personal_info_used` FIRST. Two of the six decisions read NO personal information at all,
-- and those two are the ones the product is built on: the refusal is computed from blame ancestry
-- and control deltas, not from anyone's identity or history. A register that honestly reports an
-- empty array for the flagship decision is a stronger statement than a paragraph claiming less.
--
-- The decisions that DO read personal information are the ones SEC-3 (the Attribution Rule)
-- governs. Each satisfies its four conditions: it is a precondition of a state transition the
-- database enforces; it is computed from a pre-committed, versioned, customer-signed policy that
-- predates the data it scores; it is recomputable from primary facts by a third party; and the
-- scored person can obtain their own score and its derivation from `mainline_qa.v_my_record`.
--
-- `standing_quorum` SHIPS INERT and the register says so. W = 1.0 for every hazard class, so
-- quorum is one signature, which is the behaviour with the feature switched off. The inertness is
-- itself a dated object in `mainline_meas.person_measure_policy`, which is what makes
-- "counsel-gated" a row the database requires rather than a project state: a standing score
-- computed over data predating the policy is not an insertable row (23514).
--
-- FORMATTING NOTE: every string literal below is written on ONE line, however long. Adjacent
-- string-literal concatenation across newlines is standard SQL, but this band was authored with no
-- CockroachDB cluster reachable to prove the lexer accepts it, and a seed that fails to parse in
-- an unattended provisioning run is a worse trade than a long line. Apostrophes are doubled.

INSERT INTO mainline.adm_decision_class
  (class_id, description, personal_info_used, effect_on_individual, disclosure_text) VALUES

  ('recall_admission',
   'Which prior incidents are admitted as precursors to a proposed weakening of a control, which are surfaced as advisory, and which are silenced. Deterministic fusion over four retrieval channels under an anchored, cosigned policy version.',
   ARRAY[]::STRING[],
   'None. The decision ranges over documents and events, not people. No output of this decision characterises any individual.',
   'MAINLINE decides automatically which earlier incidents are shown to you before you may weaken a safety control. That decision uses records of events and documents. It does not use information about you, and it does not produce any assessment of you.'),

  ('blocking_check_materialisation',
   'Whether a proposed change is a weakening whose blame ancestry contains a serious or fatal event, and therefore whether an obligation row is created that the database will refuse to merge over. Severity and virulence are projected from the blame closure by trigger, never supplied by the writer.',
   ARRAY[]::STRING[],
   'None directly. It may block work you proposed until an obligation is dispositioned, but the decision reads no information about you and forms no view of you.',
   'MAINLINE decides automatically whether a proposed change weakens a control that an earlier incident wrote. If it does, the system requires a signed disposition before the change can be merged. This decision is based on the history of the document and the incident record, not on any information about the person proposing the change.'),

  ('cue_synthesis',
   'Generation of retrieval cues — short paraphrases of an incident''s mechanism, preconditions, control failures and recurrence tests — used to find that incident again later. Model-authored and marked is_derived.',
   ARRAY['names and role titles appearing in the source incident document, where the source document contains them'],
   'None. A synthesised cue may never be quoted to a human without its source event, because a cue is a machine paraphrase of a real workplace incident and displaying it alone would be an unattributed machine statement about real people.',
   'MAINLINE uses a language model to write short summaries of past incidents so they can be found again. Where an incident report names people, those names may appear in the source text the model reads. These summaries are never shown without the original record they came from.'),

  ('clearance_legality',
   'Whether the disposition kind a person is attempting to sign is legal for the ancestral virulence of the control being weakened, and whether a countersignature, a foreign-organisation signer, or a higher rank is required. Composite foreign key against the customer-approved clearance lattice; the signer''s rank, organisation and competency are projected from mainline.person and never accepted from the client.',
   ARRAY['signer_sub', 'rank', 'org', 'competency_snapshot'],
   'May refuse a disposition you attempted to sign, and may require your signature to be countersigned by a person of higher rank or from another organisation. It produces no score, rating or characterisation of you; it compares your recorded authority against a rule your employer approved and dated.',
   'MAINLINE decides automatically whether you are permitted to sign off a particular kind of safety decision. The decision uses your recorded role, rank, organisation and current competencies as held in your employer''s HR system, checked against a rule set your employer has approved and signed. You can obtain the rule that was applied, the values used, and the result.'),

  ('override_escalation',
   'Whether an emergency override requires escalating rank and countersignature because of prior overrides recorded against the same person across permits. Projection from override_ledger; no ceiling (MI29).',
   ARRAY['signer_sub', 'count of prior emergency overrides signed by that person'],
   'Raises the rank and countersignature required for you to sign a further emergency override. It is a count of your own recorded acts, not a judgement about you, and it never blocks a permit outright — it makes the record louder.',
   'If you sign emergency overrides repeatedly, MAINLINE automatically requires progressively more senior countersignature for each further one. This uses the count of overrides you have previously signed. You can obtain that count and the rule applied to it.'),

  ('standing_quorum',
   'Derived signing authority (standing) used to set the signature quorum for a hazard class. SHIPS INERT: W = 1.0 for every hazard class, so quorum is one signature, which is the behaviour with the feature switched off. Governed by mainline_meas.person_measure_policy, which refuses a score computed over data predating the policy (23514).',
   ARRAY['signer_sub', 'rank', 'competency_snapshot', 'disposition history under a signed policy'],
   'Currently none — the weighting is 1.0 for every hazard class, so the number of signatures required is unchanged. If your employer activates it under a signed and notified policy, it may increase the number of signatures required on a decision.',
   'MAINLINE can be configured by your employer to derive a signing-authority level for named people and use it to decide how many signatures a safety decision requires. This capability is currently inactive and has no effect. It cannot be activated without a signed, dated and notified policy from your employer, and if it is activated you can obtain your own level and the full derivation of it.');
