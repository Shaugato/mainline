-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI03, MI01
-- I: I06
-- COUNSEL-GATED: no
-- RATIONALE: MinHash/LSH banding expressed as a PURE EQUALITY JOIN on a primary index — no GIN, no similarity operator, no extension — because the candidate-generation step of the identity matcher sits on the gate's latency path, and a join whose plan cannot flip is a latency budget you can actually promise.
--
-- migration:  0030_clause_band
-- band:       0024-0031, 0047-0049 · dm-spine
-- statements: 1
-- source:     ARCHITECTURE.md §5.3 (verbatim shape; constraints named per DM-10) · §5.3
--             Conservation of Blame Mass · datamodel.md DM-6, DM-10
-- requires:   0029 mainline.clause_version
-- projects:   nothing. Band hashes are computed by the matcher from `canon_text` and are inputs,
--             not gate scalars — a forged band row can only ADD a candidate, never remove one.
--             See WHY THIS TABLE IS NOT A PROJECTION below; that asymmetry is the whole reason
--             P2 does not bind here.
-- sqlstate:   23503 on fk_version; 23514 on band_no_nonneg; 23505 on clause_band_pk
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- WHAT LOCALITY-SENSITIVE HASHING BUYS, IN ONE PARAGRAPH. Comparing a new clause against every
-- historical clause in a site is quadratic and unaffordable. MinHash reduces each clause's
-- shingle set to a signature; the signature is cut into B bands; two clauses whose signatures
-- agree on ANY band are candidates. Agreement on a band is EQUALITY of an INT8, so candidate
-- generation is `SELECT … WHERE site_id = $1 AND band_no = $2 AND band_hash = $3` — a seek into
-- this table's primary index, B times, and nothing else. The expensive comparison then runs over
-- a handful of candidates instead of the corpus.
--
-- THE PRIMARY KEY IS THE ENTIRE TABLE. (site_id, band_no, band_hash, clause_uuid, commit_id):
-- every column, in the order the lookup constrains them. There is no secondary index because
-- there is no second access pattern — the matcher only ever probes forward, and a covering
-- primary index means the seek returns the candidate without touching another key. That is also
-- why there are no column families: a five-column row with no cold half has nothing to split.
--
-- WHY THIS TABLE IS NOT A PROJECTION, AND WHY THAT IS SOUND. Every other cross-row scalar in this
-- band is trigger-written from an authoritative table (P2), because a writer who chooses the value
-- chooses the gate's answer. Band hashes are the exception, and the exception has a proof rather
-- than an excuse: a band row can only ADD a candidate pair to the matcher's comparison set. It
-- cannot remove one, because removal would require deleting a row from an append-only table that
-- no application role holds DELETE on (MI01). So the worst a forged band row achieves is that the
-- matcher does more work and then rejects the candidate on the real comparison. A forged row
-- cannot hide an ancestor.
--
-- And if the matcher MISSES an ancestor — because a band was never written, or because
-- adversarial paraphrase defeated MinHash outright — the miss does not become a silent pass. It
-- becomes a row in mainline.identity_residue (0049) with `reason = 'unmatched'` and no
-- disposition, which BLOCKS the merge under MI03. That is Conservation of Blame Mass: every
-- ancestor clause carrying a blame edge to a severity ≥ 4 event is, in commit c, matched, matched
-- through a recorded split/merge, or explicitly absent with a signed disposition. There is no
-- fourth state. A successful evasion of the matcher therefore produces an orphaned blood-written
-- obligation, which presents as deletion of a control written by a fatality and raises a STRONGER
-- gate than the one it evaded. Rewording changes WHICH gate you fail, never WHETHER you fail.
--
-- `fk_version` IS ADDED HERE AND §5.3 DOES NOT SPECIFY IT. The composite FK onto
-- (clause_uuid, commit_id) — the UNIQUE declared on 0029 for exactly this purpose — means a band
-- row cannot name a version that does not exist. Without it, a phantom candidate survives into
-- the comparison step and the matcher spends its budget resolving a row that was never there. It
-- is cheap: this table is written in the same transaction as the version it bands.
--
-- `band_no` IS INT2 AND STARTS AT 0. The number of bands is a matcher parameter (a trade between
-- recall and comparison cost), it is recorded with the run rather than in the schema, and it is
-- small. `band_no_nonneg` is the only shape constraint a single row can support; that B is
-- consistent across a site's corpus is a property of the matcher, checked by the recall
-- evaluation harness rather than by the database, because a CHECK cannot see the other rows.
--
-- NO TTL, NO PRUNING. §4.1 law 13: row-level TTL exists on exactly three tables and none of them
-- is in schema `mainline`. A band row is a contemporaneous business record of how the matcher saw
-- the corpus at the time, and deleting it would make a past matching decision unreproducible —
-- which is the one thing a disclosure bundle must never be.
--
-- UNVERIFIED ON THIS MACHINE: no CockroachDB v26.2 was reachable when this band was authored, so
-- this statement has not been executed. See tests/integration/schema/test_mi_spine.py.

CREATE TABLE mainline.clause_band (
  site_id     UUID  NOT NULL,
  band_no     INT2  NOT NULL,
  band_hash   INT8  NOT NULL,
  clause_uuid UUID  NOT NULL,
  commit_id   BYTES NOT NULL,
  CONSTRAINT clause_band_pk PRIMARY KEY (site_id, band_no, band_hash, clause_uuid, commit_id),
  CONSTRAINT fk_version FOREIGN KEY (clause_uuid, commit_id)
    REFERENCES mainline.clause_version (clause_uuid, commit_id),
  CONSTRAINT band_no_nonneg CHECK (band_no >= 0)
);
