-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI01, MI09
-- I: I04
-- COUNSEL-GATED: no
-- RATIONALE: `parent_gen` is denormalised so a reachability walk prunes on a plain column instead of joining back to commit_obj on every hop, and it is PROJECTED from commit_obj rather than taken from the inserter, because a writer who supplies a parent's generation chooses which ancestors a bisect can reach.
--
-- migration:  0025_commit_edge
-- band:       0024-0031, 0047-0049 · dm-spine · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- statements: 1
-- source:     ARCHITECTURE.md §5.2 (verbatim shape; constraints named per DM-10, index inline per
--             DM-6) · §4.1 law 1 (CHECK sees only the row being written) · datamodel.md DM-10
-- requires:   0024 mainline.commit_obj
-- projects:   parent_gen ← mainline.commit_obj.gen (P2). Owed to TRIGGER-MAP.yaml and to
--             `fn_commit_edge_project` in band 0130-0199, which must RAISE P0001 when the parent
--             commit row is absent.
-- sqlstate:   23503 on fk_child / fk_parent; 23514 on no_self_parent / parent_ord_nonneg /
--             parent_gen_nonneg / child_id_is_sha256 / parent_id_is_sha256;
--             23505 on commit_edge_pk and parent_listed_once
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ONE ROW PER PARENT, ORDERED. `parent_ord = 0` is THE FIRST PARENT — the mainline — and every
-- other ordinal is a merged-in branch. The distinction is not cosmetic: "the first-parent path"
-- is the history a human reads as "what this branch did", and a merge commit that reversed the
-- roles of its parents would silently relabel which side of a merge was the trunk. The primary
-- key (child_id, parent_ord) makes the ordering part of identity, so it cannot be shuffled by an
-- UPDATE that touches nothing else.
--
-- WHY `parent_gen` IS DENORMALISED, AND WHY THAT MAKES IT A PROJECTION AND NOT A CONVENIENCE.
-- A reachability walk ("is commit A an ancestor of commit B") prunes on generation: any parent
-- whose gen is below the target's gen cannot lead anywhere useful. With `parent_gen` on the edge,
-- that prune is a predicate on the row the walk already has. Without it, every hop joins back to
-- mainline.commit_obj — which on a deep history is the difference between a bounded walk and a
-- fan-out.
--
-- But the moment a column PRUNES A SEARCH, an inserter who chooses its value chooses what the
-- search can find. A forged low `parent_gen` makes a real ancestor invisible to a walk that
-- prunes on it — and an invisible ancestor is an unrecalled precursor, which is the exact failure
-- this product exists to make impossible. There is no error anywhere in that history: the row is
-- present, the FK holds, the walk terminates, and the answer is wrong. So P2 applies with full
-- force: `parent_gen` is written by a trigger from mainline.commit_obj, and that trigger RAISEs
-- P0001 when the parent has no row. Until band 0130-0199 lands, this column is CLIENT-SUPPLIED,
-- and this comment is the record of that fact rather than a description of a control that exists.
--
-- THE `gen` LAW LIVES HERE, NOT ON commit_obj. §5.2 states `gen = 1 + max(parent.gen)`. A `CHECK`
-- cannot express it (§4.1 law 1: a CHECK sees only the row being written, so it can never see the
-- parent), and a trigger on mainline.commit_obj cannot either, because at the moment a commit row
-- is inserted its edges do not exist yet. This table is the only place where both ends are known
-- in one row. `fn_commit_edge_project` (band 0130-0199) therefore does both halves in one pass:
-- it overwrites `parent_gen` from mainline.commit_obj, and it RAISEs when the child's own `gen`
-- is not strictly greater than it. Strictly greater — not exactly one more — because the exact
-- equality is over max() across ALL of a child's edges, and a row-level trigger sees one edge.
-- Strict increase over every edge is the property bisect actually needs: it is what makes the
-- generation ordering a topological ordering, and therefore what makes the PK-ordered range scan
-- in 0029 a correct substitute for a graph walk.
--
-- NO COLUMN IS ADDED TO CARRY THE CHILD'S OWN `gen`. It was considered: a `child_gen` column
-- would turn the law above into a plain-column CHECK — the REFUSE half of the kernel idiom —
-- which is strictly better than a trigger, since a CHECK survives `ALTER TABLE … DISABLE
-- TRIGGER`. It is not done here because BOTH columns would then be projections of the same table,
-- and a projection pair that is written by the trigger it is meant to constrain adds a second
-- forgery surface for the same law. If the unwelding suite later shows this weld's refusal depth
-- is 1 and that is judged too thin, the change is additive: one column, one CHECK, one
-- TRIGGER-MAP row. It is recorded here so the decision is visible rather than absent.
--
-- `no_self_parent` IS THE ONLY CYCLE A PLAIN CHECK CAN SEE. A commit that is its own parent is a
-- one-node cycle, and it is refusable from the row alone. Longer cycles are impossible for a
-- different and better reason: `child_id` is the SHA-256 of an envelope that names `parent_id`,
-- so a cycle would require a hash preimage. The database enforces the trivial case; the
-- arithmetic enforces the rest. Both facts are worth having, because the second one stops being
-- true the instant someone inserts an edge whose child_id was not derived from its envelope —
-- which is what `id_is_sha256` on 0024 and `trappoint-verify` are for.
--
-- `parent_listed_once` (UNIQUE (child_id, parent_id)) IS NEW HERE, not in §5.2. A commit that
-- lists the same parent at two ordinals is not merely odd: it double-counts that subtree in any
-- reachability or blame-mass walk that does not deduplicate, and it makes `max(parent.gen)`
-- ambiguous about how many parents there really were. It is refusable from two columns, so it is.
--
-- `desc_walk (parent_id, child_id)` IS THE DESCENDANT DIRECTION. The primary key answers "who are
-- my parents"; this index answers "who are my children", which is the direction propagation and
-- "does this fix reach the fleet" queries run in. Both directions matter, so both are indexed.
--
-- UNVERIFIED ON THIS MACHINE: no CockroachDB v26.2 was reachable when this band was authored, so
-- this statement has not been executed. See tests/integration/schema/test_mi_spine.py.

CREATE TABLE mainline.commit_edge (
  child_id   BYTES NOT NULL,
  parent_ord INT2  NOT NULL,   -- 0 = first parent (the mainline)
  parent_id  BYTES NOT NULL,
  parent_gen INT8  NOT NULL,   -- PROJECTED from mainline.commit_obj.gen (P2); prunes reachability
  CONSTRAINT commit_edge_pk PRIMARY KEY (child_id, parent_ord),
  CONSTRAINT fk_child  FOREIGN KEY (child_id)  REFERENCES mainline.commit_obj (commit_id),
  CONSTRAINT fk_parent FOREIGN KEY (parent_id) REFERENCES mainline.commit_obj (commit_id),
  CONSTRAINT parent_listed_once UNIQUE (child_id, parent_id),
  CONSTRAINT child_id_is_sha256 CHECK (length(child_id) = 32),
  CONSTRAINT parent_id_is_sha256 CHECK (length(parent_id) = 32),
  CONSTRAINT parent_ord_nonneg CHECK (parent_ord >= 0),
  CONSTRAINT parent_gen_nonneg CHECK (parent_gen >= 0),
  CONSTRAINT no_self_parent CHECK (child_id <> parent_id),
  INDEX desc_walk (parent_id, child_id)
);
