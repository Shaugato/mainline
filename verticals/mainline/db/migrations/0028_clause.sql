-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI01, MI03
-- I: I01
-- COUNSEL-GATED: no
-- RATIONALE: `clause_uuid` is minted once and never reused, so a clause's identity survives every rewording of its text — which is what makes "this sentence is the same obligation the 2019 fatality wrote" a claim about a key rather than a claim about a string.
--
-- migration:  0028_clause
-- band:       0024-0031, 0047-0049 · dm-spine · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- statements: 1
-- source:     ARCHITECTURE.md §5.3 (verbatim shape; constraints named per DM-10, index inline per
--             DM-6) · §5.3 Conservation of Blame Mass · §6.3 (the vector prefix)
-- requires:   0024 mainline.commit_obj
-- projects:   nothing. `activity_root` is AUTHORITATIVE here and is the source that
--             mainline.clause_embedding (0031) projects its prefix-2 column FROM.
-- sqlstate:   23503 on fk_birth_commit / fk_head_commit / fk_retired_commit;
--             23514 on activity_root_stated; 23505 on clause_pk
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- THE @wId ANALOGUE. Akoma Ntoso separates the immutable work-level identifier of a provision
-- (@wId) from its printed label (@eId, '7.3.2(b)'), because clause 7.3.2(b) of the 2024 edition
-- and clause 8.1.4 of the 2029 edition can be the same obligation, and the printed label is the
-- one thing guaranteed to change when a document is renumbered. `clause_uuid` is the @wId.
-- `printed_label` and `ordinal` live on mainline.clause_version (0029) where they belong: with
-- the version, as presentation, NEVER as identity.
--
-- `head_commit` IS THE ONLY MUTABLE COLUMN IN THIS FILE, and that sentence is the file's design.
-- Everything a clause IS lives in its versions; this row is the stable handle plus one moving
-- pointer to the current version's commit. Keeping the mutable surface to one column means the
-- append-only trigger in band 0130-0199 (MI01) has exactly one exemption to carve, and an
-- exemption you can state in one clause is one an auditor can check.
--
-- ALL THREE COMMIT POINTERS CARRY A FOREIGN KEY, WHICH §5.3 DOES NOT REQUIRE. §5.3 puts an FK on
-- `birth_commit` only and calls the other two "pointer only". They are FK'd here because a
-- dangling commit pointer on a clause is not a stale cache entry — it is an exhibit that names a
-- commit nobody can produce. "This obligation was retired in commit 9f3c…" is a sentence that
-- either resolves or is worthless in front of a regulator, and 23503 at write time is
-- incomparably cheaper than discovering it at disclosure. mainline.commit_obj is append-only and
-- content-addressed, so the FK never blocks a legitimate write and never cascades.
--
-- `activity_root` IS THE VECTOR PREFIX, AND THAT MAKES IT A REACHABILITY DECISION.
-- C-SPANN maintains a SEPARATE k-means tree per distinct prefix value, so `(site_id,
-- activity_root)` on mainline.clause_embedding (0031) does not filter a result set — it SELECTS
-- THE TREE THAT IS SEARCHED. A clause embedded under the wrong activity root is not ranked lower;
-- it is unreachable, by every arm, forever, with no refusal anywhere and no row that is wrong.
-- THIS TABLE IS THE AUTHORITATIVE SOURCE for that value. 0031 projects it from here, and its
-- trigger must RAISE when this row is absent. The archival taxonomy is FUNCTIONAL (ISO 15489 /
-- NAA): classified by function and activity, not by asset or org unit — which is precisely why
-- blame survives the churn. Asset tags and org charts are recut every three years; "isolating
-- stored energy before intrusive work" is not.
--
-- WHY THERE IS NO `site_id` FK. mainline.site (0021) exists and is the authoritative source for
-- site_role / site_code / tenant_id (DM-3). An FK from here to it is deliberately NOT added,
-- consistently with the rest of the schema: `site_id` appears on ~40 tables, and forty FKs onto
-- one row per site turns every write in the system into a read of the same range — a hotspot with
-- no integrity benefit that RLS and the projection triggers do not already provide. The site's
-- authority is exercised through PROJECTION, not through referential integrity.
--
-- NO `UNIQUE (site_id, …)` ON THIS TABLE. There is no natural key for a clause. Two clauses in
-- one site may have identical text, identical printed labels and identical anchors and still be
-- two obligations — that is what happens when a procedure is duplicated across two units — and a
-- uniqueness constraint that guessed otherwise would silently merge two obligations into one,
-- which is Conservation of Blame Mass running backwards. Identity is asserted by the matcher and
-- its failures are conserved into mainline.identity_residue (0049), not prevented by a constraint
-- that cannot know.
--
-- UNVERIFIED ON THIS MACHINE: no CockroachDB v26.2 was reachable when this band was authored, so
-- this statement has not been executed. See tests/integration/schema/test_mi_spine.py.

CREATE TABLE mainline.clause (
  clause_uuid    UUID   NOT NULL,   -- the @wId analogue. Immutable. Minted once. Never reused.
  site_id        UUID   NOT NULL,
  birth_commit   BYTES  NOT NULL,
  activity_root  STRING NOT NULL,   -- AUTHORITATIVE. 0031 projects its vector prefix FROM here.
  head_commit    BYTES  NULL,       -- pointer only; the ONLY mutable column in this file
  retired_commit BYTES  NULL,
  CONSTRAINT clause_pk PRIMARY KEY (clause_uuid),
  CONSTRAINT fk_birth_commit   FOREIGN KEY (birth_commit)   REFERENCES mainline.commit_obj (commit_id),
  CONSTRAINT fk_head_commit    FOREIGN KEY (head_commit)    REFERENCES mainline.commit_obj (commit_id),
  CONSTRAINT fk_retired_commit FOREIGN KEY (retired_commit) REFERENCES mainline.commit_obj (commit_id),
  CONSTRAINT activity_root_stated CHECK (activity_root <> ''),
  INDEX by_site_activity (site_id, activity_root)
);
