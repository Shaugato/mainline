-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI01, MI18
-- I: I16, I01
-- COUNSEL-GATED: no
-- RATIONALE: WITNESS DIVERSITY IS THE ONLY DEFENCE AGAINST A SPLIT VIEW, and it matters here more
-- than anywhere else in the system because the log is owned by the future defendant. A signature
-- we produce over a tree we assembled proves that we are internally consistent. A signature from
-- somebody whose interests diverge from ours proves that the tree we showed THEM is the tree we
-- are showing YOU. Only the second one is evidence, and this table is where the difference between
-- them is recorded rather than glossed.
--
-- migration:  0076_cosignature
-- band:       0072-0079z · custody · AUTHORED — verticals/mainline/db/migrations.allocation.toml;
--             see the OWNERSHIP note in 0072
-- statements: 1
-- source:     ARCHITECTURE.md §5.6 (verbatim shape), §5.6 witness-diversity paragraph · §18 slot
--             0076 · spec/wire/checkpoint.md §5.3 · docs/leads/custody.md §6 risk 1, CU-3 ·
--             C2SP tlog-witness · spec/custody/attacks.yaml A7
-- requires:   0075 mainline.ledger_checkpoint
-- owes:       (a) `fn_refuse_mutation` on this table, band 0130-0199;
--             (b) the `ledger_checkpoint.admissible` projection that COUNTS these rows — see the
--                 OPEN CONTRADICTION section of migration 0075.
-- grants:     `fk_cp` requires `SELECT ON mainline.ledger_checkpoint` for `agent_sequencer`,
--             which GRANTS.yaml does not currently give it — see the MEASURED PLATFORM FACT
--             block in 0072. This FK is verbatim from ARCHITECTURE.md §5.6, so the gap predates
--             any decision taken in this band.
-- sqlstate:   23503 on fk_cp (a cosignature for a checkpoint we never issued — this is what
--             refuses attack A7, checkpoint_swap, at the database rather than at the verifier) ·
--             23505 on cosignature_pkey (one witness, one signature, per tree size) ·
--             23514 on trust_domain_known and on operator_is_never_adverse
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- THE COMPOSITE FOREIGN KEY IS THE POINT. `(site_code, tree_size)` references the checkpoint's
-- whole primary key, so a cosignature cannot exist for a checkpoint this database never issued.
-- Attack A7 — replace a checkpoint body with a self-consistent one over a DIFFERENT tree —
-- therefore cannot bring its cosignatures with it: they are pinned to `(site, size)`, and the
-- verifier re-checks each signature against the note text it was actually made over.
--
-- ADMISSIBILITY IS COUNTED, NOT DECLARED. A checkpoint is admissible with ≥ q cosignatures across
-- ≥ q distinct `trust_domain` values, at least one with `adverse = true`. Both quantities are
-- aggregates over THIS table; neither is a column a writer may set. The projection lives in band
-- 0130-0199 and 0075 records why it is not here.
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- `operator_is_never_adverse` — THE ONE CONSTRAINT IN THIS FILE THAT EXISTS TO STOP US LYING.
--
-- The honest position, stated in `docs/leads/custody.md` §6 risk 1 and in `spec/custody/
-- checks.yaml` as `implemented_but_not_adverse`: until an insurer, a union HSR, a regulator or an
-- external auditor actually runs the 200-line cosigner, the quorum is q = 1 over OUR OWN S3 and
-- OUR OWN `ccloud` audit stream. That is a genuine witness and it is worth having. It is NOT
-- adverse in the legal sense, and a system that lets the operator's own witness carry
-- `adverse = true` can manufacture the appearance of adversarial corroboration with an UPDATE to
-- a boolean — the cheapest possible attack on the strongest claim we make.
--
--   CHECK (trust_domain <> 'operator' OR NOT adverse)
--
-- makes that specific lie a 23514, for every writer, forever. `trust_domain = 'operator'` is
-- carried in the vocabulary precisely SO THAT the self-witness has an honest name to be recorded
-- under, rather than being dressed as a regulator to fit a four-value list. The closed vocabulary
-- is itself load-bearing: diversity is `count(DISTINCT trust_domain)`, so free text would let a
-- single writer manufacture diversity out of typos.
--
-- Split-view resistance is NOT CLAIMED anywhere, and a CI grep enforces its absence from the
-- README, the deck and the video script. This constraint is what keeps the schema consistent with
-- that refusal instead of merely adjacent to it.
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
-- `received_at` IS A LOCAL CLOCK AND IS NOT EVIDENCE OF WHEN THE WITNESS SIGNED. A cosignature
-- carries no timestamp of its own under C2SP `tlog-witness`; what it attests to is
-- `(origin, size, root)`. If when-they-signed ever needs to be provable, the answer is a second
-- RFC 3161 token over the cosigned note, not a column we filled in ourselves.
--
-- WHAT A COSIGNATURE DOES NOT ATTEST TO, because the wire spec says so and an exhibit must not
-- overreach: a witness signs the origin, the size and the root. It does NOT attest to the beacon
-- lines, the TSA token or anything else in the extension block. A log that lies about its beacon
-- will still collect valid cosignatures.
--
-- NO ROW-LEVEL TTL ON THIS TABLE, EVER. See 0072.

CREATE TABLE mainline.cosignature (
  site_code    STRING      NOT NULL,
  tree_size    INT8        NOT NULL,
  witness_id   STRING      NOT NULL,   -- the C2SP note key name, e.g. 'witness.example/hsr-1'
  trust_domain STRING      NOT NULL,   -- closed vocabulary: diversity is COUNT(DISTINCT this)
  adverse      BOOL        NOT NULL,   -- adverse IN THE LEGAL SENSE; see the CHECK below
  sig          BYTES       NOT NULL,
  received_at  TIMESTAMPTZ NOT NULL DEFAULT now(),   -- local clock; not when they signed
  CONSTRAINT cosignature_pkey PRIMARY KEY (site_code, tree_size, witness_id),
  CONSTRAINT fk_cp FOREIGN KEY (site_code, tree_size)
    REFERENCES mainline.ledger_checkpoint (site_code, tree_size),
  CONSTRAINT trust_domain_known
    CHECK (trust_domain IN ('regulator', 'insurer', 'union_hsr', 'external_auditor', 'operator')),
  CONSTRAINT operator_is_never_adverse
    CHECK (trust_domain <> 'operator' OR NOT adverse),
  CONSTRAINT witness_id_stated CHECK (witness_id <> ''),
  CONSTRAINT sig_present CHECK (length(sig) > 0)
);
