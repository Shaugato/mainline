-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI06
-- I: I06
-- COUNSEL-GATED: no
-- RATIONALE: This is the DECLARATION — what the crew says they isolated — and it is deliberately the only table in the boundary trio that a human writes freely. Nothing gates on it directly. It is an input to the arithmetic in 0057, and the value of keeping it separate from the computed slice is that the DIFFERENCE between the two is what accuses: an asset in the energy closure of this declaration and absent from it is the multi-source isolation that kills people.
--
-- migration:  0055_permit_boundary
-- band:       0054-0057z · datamodel/ex-dm-gate · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- statements: 1
-- source:     ARCHITECTURE.md §5.5 (verbatim shape; constraints named per DM-10) · finding S11 ·
--             §16 MI06
-- requires:   0050 mainline.permit (RENDERED; template 0050_permit.sql.j2)
--             0054 mainline.asset_edge is NOT required by this file and is deliberately not
--             referenced: a declared tag that appears nowhere in the asset graph is the exact
--             condition `tags_unmodelled` exists to count, so an FK onto the graph would make
--             the most dangerous row in the system unrepresentable and the count always zero.
-- projects:   nothing. AUTHORITATIVE input to 0057's `tags_declared` and `under_declared`.
-- sqlstate:   23503 on fk_boundary_permit; 23514 on asset_tag_stated /
--             isolation_point_stated; 23505 on the primary key
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- READ THE `requires:` NOTE ABOVE BEFORE ADDING A FOREIGN KEY TO `asset_edge`.
--
-- It is the single most tempting change to this file and it would silently disable MI06. The
-- system's job is to notice that a crew declared an isolation on a tag the model has never heard
-- of. If declaring such a tag were a 23503, the crew would be forced to declare only tags the
-- model already knows, `tags_unmodelled` would be structurally zero, `unmodelled_asset_count`
-- would be structurally zero, and `boundary_certified_when_issued` would pass on every permit
-- forever while appearing to work. A refusal that can only ever be satisfied is not a control.
-- The unmodelled tag must be WRITEABLE so that it can be COUNTED and BLOCK.
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
-- `isolation_point_id` IS NULLABLE ON PURPOSE, AND THE NULL MEANS SOMETHING. A boundary row with
-- no isolation point is "this asset is in scope and we have not recorded the physical point at
-- which it is locked" — a real, common, intermediate state during permit preparation. Forcing a
-- value would produce placeholder text ("TBC", "N/A", " ") in the one column a person walks the
-- plant holding, and a placeholder is worse than a null because it reads as an answer. The null
-- is honest and it is countable.
--
-- What is NOT allowed is the empty string, which satisfies NOT NULL, satisfies "has a value",
-- prints as nothing, and is indistinguishable from a recorded point in every report that tests
-- `IS NOT NULL`. `isolation_point_stated` refuses it, so the column has exactly two states and
-- both are legible.
--
-- THE PRIMARY KEY IS (permit_id, asset_tag) AND CARRIES NO `kind`. A tag is either inside the
-- declared boundary or it is not; there is no second way to declare the same tag isolated on the
-- same permit. Repeating it would double-count `tags_declared` and change the arithmetic in 0057
-- without changing the plant.
--
-- ON DELETE / ON UPDATE ARE BOTH RESTRICT, EVERYWHERE IN THIS SCHEMA. A cascade rewrites history,
-- which is the offence this substrate exists to detect. Deleting a permit that has a declared
-- boundary is refused; the declared remedy for a post-completion fact is a FORK (suspend, open a
-- child, clear the child's gate afresh), never a deletion that removes the evidence of what was
-- declared.
--
-- VERIFIED 2026-08-10 against CockroachDB CCL v26.2.5 (local single node, insecure, 26257). The
-- statement applies; a blank `isolation_point_id` is refused with 23514 naming
-- `isolation_point_stated`; and — the assertion that matters — a boundary row naming a tag that
-- appears NOWHERE in `mainline.asset_edge` INSERTS, which is what keeps `tags_unmodelled`
-- countable and therefore keeps MI06 able to block. Evidence:
-- tests/integration/schema/test_mi_boundary_override.py::
-- test_mi06_an_unmodelled_tag_can_be_declared_because_counting_it_is_what_blocks.

CREATE TABLE mainline.permit_boundary (
  permit_id          UUID   NOT NULL,
  asset_tag          STRING NOT NULL,
  isolation_point_id STRING NULL,   -- NULL = not yet recorded. '' is refused; see the header.
  CONSTRAINT permit_boundary_pk PRIMARY KEY (permit_id, asset_tag),
  CONSTRAINT fk_boundary_permit FOREIGN KEY (permit_id)
    REFERENCES mainline.permit (permit_id)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT asset_tag_stated CHECK (asset_tag <> ''),
  CONSTRAINT isolation_point_stated
    CHECK (isolation_point_id IS NULL OR isolation_point_id <> '')
);
