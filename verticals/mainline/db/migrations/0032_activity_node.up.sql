-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI16, MI01
-- I: I13, I01
-- COUNSEL-GATED: no
-- RATIONALE: Blame has to survive twenty-two years, and the only classification axis that survives that long is the FUNCTION PERFORMED — asset tags and org charts churn every three years, so a taxonomy keyed on either would have silently severed every blame path in the corpus before the first permit was ever refused.
--
-- migration:  0032_activity_node
-- band:       0032-0036 · dm-event-severity (activity taxonomy, events, and the severity record)
-- statements: 1
-- source:     ARCHITECTURE.md §5.4 (verbatim shape; constraints named per DM-10, index inline per DM-6)
-- requires:   0002 CREATE SCHEMA mainline
-- consumed:   0040 event_cue.scope_id · 0046 event_bond.scope_id · the LMB scope tree
-- sqlstate:   23514 on l1_frozen / level_in_range / induced_by_closed / the parentage pair;
--             23505 on activity_node_path_unique; 23503 on fk_parent_scope
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- THE ARCHIVAL TAXONOMY IS FUNCTIONAL (ISO 15489 / NAA), NOT STRUCTURAL.
-- A label is A FUNCTION PERFORMED — "isolating stored energy before intrusive work" — never a
-- thing ("the 4160 V switchroom"), never a place ("north decline"), never an org unit
-- ("Maintenance Planning"). That single rule is WHY blame survives: the switchroom is
-- decommissioned, the decline is backfilled, the department is reorganised, and the function is
-- still being performed by somebody at 3 a.m. twenty years later.
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
-- THREE LEVELS, AND WHY THE COUNT IS FIXED AT THREE (ISAD(G) multi-level description):
--
--   1  fonds   the ICMM Material Unwanted Event register. 12-25 rows. FROZEN.
--   2  series  a coherent body of activity within the function
--   3  file    the individual activity a permit is actually written against
--
-- The level is not decoration and it is not a display hint — it is a PHYSICAL PARTITION KEY.
-- `mainline.event_cue` writes one row per level (Level-Materialised Bonds), and each of those
-- rows lands in a different C-SPANN tree because `scope_id` is a vector-index prefix column.
-- That is what grades the tree sizes (fonds large, file small) and what turns "which level did
-- this hit at" into a retrieval feature: a file-level hit is stronger evidence than a
-- fonds-level hit, and the ranker is entitled to say so.
--
-- WHY LEVEL 1 IS FROZEN, AS A CHECK AND NOT AS A POLICY (`l1_frozen`).
-- `activity_root` — the level-1 code — is baked into the physical vector index as a prefix
-- value. C-SPANN maintains a separate K-means tree per distinct prefix value, so changing a
-- level-1 code is not an UPDATE; it is a re-partition of the index, i.e. a migration with a
-- rebuild. A row that could be re-inducted at level 1 is a row that could silently invalidate
-- every embedding beneath it, and the failure would present as "recall got worse", months later,
-- with no error anywhere. `CHECK (level <> 1 OR frozen = true)` makes the invalidation
-- unrepresentable instead of merely discouraged.
--
-- THE PARENTAGE PAIR IS STRICTLY STRONGER THAN §5.4 AND DELIBERATELY SO.
-- §5.4 leaves `parent_scope` nullable with no shape rule. Two named CHECKs close it:
-- `l1_has_no_parent` (a fonds is a root, so a parent on one means the level column is lying)
-- and `below_l1_has_a_parent` (a series or file with no parent is an orphan, and an orphan is
-- invisible to the ancestor walk that MI16 depends on — the bonded severity-5 event would be
-- silently unreachable from the permit's activity node, which is precisely the failure MI16
-- exists to prevent). Neither reads another row: both see only the row being written.
-- If v26.2 rejects either, DELETE THAT CONSTRAINT LINE and nothing else moves; the assertion
-- then lives in tests/integration/schema/test_mi_event_severity.py.
--
-- `activity_root` IS A PROJECTION AND IS NOT YET ENFORCED AS ONE (P2, honest).
-- It is the level-1 ancestor's code, denormalised onto every descendant so the vector prefix is
-- one column read rather than a two-hop walk. Authoritative source: THIS TABLE, the level-1
-- ancestor row reached through `parent_scope`. Until `fn_activity_root_project`
-- (band 0130-0199, dm-functions-triggers) writes it and RAISEs P0001 when the ancestor is
-- absent, the column is client-supplied and this comment is the only thing saying so. It must
-- appear in TRIGGER-MAP.yaml as: activity_root ⇄ fn_activity_root_project ⇄ mainline.activity_node ⇄ P0001.
--
-- `induced_by` RECORDS WHO INVENTED THE CATEGORY, and the three values are not equivalent:
-- `icmm_mue` is the buyer's own register, `human` is a person who wrote it down, `llm_induced`
-- is a model that proposed a category and had it accepted. A taxonomy is an interpretive act;
-- a schema that cannot say which of those three produced a node cannot later answer "who
-- decided this incident and this permit were about the same thing", and that question is the
-- whole product.

CREATE TABLE mainline.activity_node (
  scope_id      UUID   NOT NULL DEFAULT gen_random_uuid(),
  site_id       UUID   NOT NULL,             -- authoritative source: mainline.site (DM-3)
  level         INT2   NOT NULL,             -- 1 fonds · 2 series · 3 file
  parent_scope  UUID   NULL,
  label         STRING NOT NULL,             -- a FUNCTION PERFORMED, never a thing or a place
  activity_root STRING NOT NULL,             -- PROJECTED (pending): the level-1 ancestor's code
  taxonomy_ver  INT4   NOT NULL,
  induced_by    STRING NOT NULL,
  frozen        BOOL   NOT NULL DEFAULT false,
  CONSTRAINT activity_node_pk PRIMARY KEY (scope_id),
  CONSTRAINT fk_parent_scope FOREIGN KEY (parent_scope)
    REFERENCES mainline.activity_node (scope_id),
  CONSTRAINT activity_node_path_unique UNIQUE (site_id, taxonomy_ver, level, label),
  CONSTRAINT level_in_range CHECK (level BETWEEN 1 AND 3),
  CONSTRAINT induced_by_closed CHECK (induced_by IN ('icmm_mue', 'llm_induced', 'human')),
  CONSTRAINT l1_frozen CHECK (level <> 1 OR frozen = true),
  CONSTRAINT l1_has_no_parent CHECK (level <> 1 OR parent_scope IS NULL),
  CONSTRAINT below_l1_has_a_parent CHECK (level = 1 OR parent_scope IS NOT NULL),
  CONSTRAINT label_stated CHECK (label <> ''),
  CONSTRAINT activity_root_stated CHECK (activity_root <> ''),
  CONSTRAINT taxonomy_ver_positive CHECK (taxonomy_ver >= 1),
  INDEX by_parent (parent_scope, level),
  INDEX by_root (site_id, taxonomy_ver, activity_root, level)
);
