-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI01, MI09
-- I: I04
-- COUNSEL-GATED: no
-- RATIONALE: A ref is a NAME for a head commit, and `protected` is the column that says this name is a permit-to-work whose merge the database refuses until every recalled precursor carries a signed disposition — the product's one sentence, expressed as a boolean on a row.
--
-- migration:  0026_ref
-- band:       0024-0031, 0047-0049 · dm-spine · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- statements: 1
-- source:     ARCHITECTURE.md §5.2 (verbatim shape; constraints named per DM-10, index inline per
--             DM-6) · §0 (what MAINLINE is) · §5.5 (the gate reads the ref this names)
-- requires:   0024 mainline.commit_obj
-- projects:   gen_head ← mainline.commit_obj.gen (P2), for the commit named by head_id. Owed to
--             TRIGGER-MAP.yaml and to `fn_ref_head_project` in band 0130-0199, which must RAISE
--             P0001 when head_id names no commit.
-- sqlstate:   23503 on fk_head; 23514 on ref_kind_closed / ref_name_stated / gen_head_nonneg;
--             23505 on ref_pk
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- THIS IS THE ONLY MUTABLE TABLE IN THE SPINE. Everything else in band 0024-0031 is append-only:
-- a commit is content-addressed, a clause version is a new row, a band row is a fact about a
-- version. A REF MOVES. That is its whole job — it is the mutable pointer that makes an immutable
-- DAG usable — and it is why every other design decision in this band works to keep the mutable
-- surface down to one column on one table.
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
-- `protected` IS THE PRODUCT, IN ONE COLUMN. "The permit-to-work is a protected branch whose
-- merge the DATABASE refuses until every recalled precursor carries a signed disposition." A ref
-- with `protected = true` is one whose head may not advance except through the gate transaction
-- in §6.5 — and the refusal that makes that true is NOT here. It is `gate_closed_when_issued` on
-- mainline.permit and `cr_gate_closed_when_merged` on mainline.change_request (band 0050-0065),
-- plus the epoch pin on mainline.merge_record (0071). This column is the DECLARATION; those are
-- the REFUSALS. Stating the difference in the file rather than implying the flag does work by
-- itself is the difference between a design and a claim.
--
-- WHY A ref IS NOT A FOREIGN KEY TARGET FOR THE GATE. It would be natural to hang the gate off
-- this table. It is wrong, and the reason is §4.1 law 3: SERIALIZABLE orders writes but does not
-- prevent LATE ARRIVAL. A precursor inserted at T+ε, after a merge at T, is a perfectly
-- serializable history. The pin that makes late arrival impossible is a composite FK onto
-- (subject_id, epoch) with ON UPDATE RESTRICT, and a ref has no epoch because a ref is not a
-- transition — it is a name. Refs move forward many times; a permit merges once, ever.
--
-- `ref_name` IS THE PRIMARY KEY AND IT IS HUMAN-READABLE ON PURPOSE. 'site/marrindal/main',
-- 'permit/WO-88213', 'cr/MOC-2029-114'. An exhibit that names a branch by UUID is an exhibit
-- nobody can check against the operational record; the site's own work-order number is the join
-- to the world outside this database. The cost is that a rename is a delete plus an insert, which
-- is correct: renaming a permit's branch IS creating a different name for the same history, and
-- the history is addressed by hash anyway.
--
-- `site_id` IS NULLABLE AND `ref_kind` IS NOT. Some refs are not site-scoped — a fleet-wide
-- lesson ref spans sites by construction, and forcing it to pick one would be a lie that RLS
-- would then enforce. `by_site (site_id, ref_kind)` indexes the common case ("list this site's
-- permit branches") and tolerates the NULL rows sitting together at the front of the index.
--
-- `gen_head` IS A PROJECTION, NOT A CACHE. It is the generation of the commit `head_id` names,
-- and it exists so that "is this ref ahead of that one" is a comparison of two integers instead of
-- two lookups. Same argument as `parent_gen` on 0025, same conclusion: a writer who supplies it
-- chooses the answer to an ordering question the gate path asks, so it is written by a trigger
-- from mainline.commit_obj and the trigger RAISEs when there is no such commit. Until band
-- 0130-0199 lands it is client-supplied, and this file says so.
--
-- `ref_kind` IS A CLOSED `CHECK` AND NOT AN FK'd VOCABULARY, unlike mainline_ops.outbox_kind
-- (DM-11). The distinction DM-11 draws is whether a writer OUTSIDE the schema supplies the value:
-- an outbox kind is written by application code and routed by a changefeed, where a typo is
-- dropped silently. A ref kind is written by the repository service itself, in the same
-- transaction as the commit it names, and a typo there is a 23514 at the first test. Six values,
-- closed set, no lookup table.
--
-- UNVERIFIED ON THIS MACHINE: no CockroachDB v26.2 was reachable when this band was authored, so
-- this statement has not been executed. See tests/integration/schema/test_mi_spine.py.

CREATE TABLE mainline.ref (
  ref_name  STRING NOT NULL,   -- 'site/marrindal/main', 'permit/WO-88213', 'cr/MOC-2029-114'
  ref_kind  STRING NOT NULL,
  site_id   UUID   NULL,       -- NULL for fleet-wide refs; see by_site
  head_id   BYTES  NOT NULL,
  gen_head  INT8   NOT NULL,   -- PROJECTED from mainline.commit_obj.gen for head_id (P2)
  protected BOOL   NOT NULL DEFAULT false,   -- the permit-to-work branch. Declaration, not gate.
  CONSTRAINT ref_pk PRIMARY KEY (ref_name),
  CONSTRAINT fk_head FOREIGN KEY (head_id) REFERENCES mainline.commit_obj (commit_id),
  CONSTRAINT ref_kind_closed CHECK (ref_kind IN
    ('branch', 'tag', 'permit', 'change_request', 'as_operated', 'lesson')),
  CONSTRAINT ref_name_stated CHECK (ref_name <> ''),
  CONSTRAINT head_id_is_sha256 CHECK (length(head_id) = 32),
  CONSTRAINT gen_head_nonneg CHECK (gen_head >= 0),
  INDEX by_site (site_id, ref_kind)
);
