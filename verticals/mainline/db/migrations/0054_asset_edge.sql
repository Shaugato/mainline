-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI06
-- I: I06
-- COUNSEL-GATED: no
-- RATIONALE: A dependency edge consumed by a gate is COMPUTED, never declared (I06). This table is the modelled energy/control graph the computation runs over, and its completeness is therefore a safety property in its own right: an asset with no edges here is UNKNOWN, and finding S11 rules that unknown BLOCKS rather than passes. Everything the boundary certificate can honestly say about a permit is a statement about this graph.
--
-- migration:  0054_asset_edge
-- band:       0054-0057z · datamodel/ex-dm-gate · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1). The band is the
--             surviving half of the revoked `dm-gate` claim: `permit`, `change_request`,
--             `permit_clause` and `cr_clause` are SUBSTRATE and are rendered at 0050-0053z;
--             the asset graph, the declared boundary, the computed slice and the certificate
--             are VERTICAL — a second TRAPPOINT vertical gates on something other than
--             hazardous energy — so they are authored here.
-- statements: 1
-- source:     ARCHITECTURE.md §5.5 "Declared scope, the exposure slice, and the boundary
--             certificate" (verbatim shape; constraints named per DM-10) · finding S11 ·
--             §16 MI06 · §4.1 I06
-- requires:   0001a CREATE SCHEMA mainline (RENDERED)
-- projects:   nothing. This table is AUTHORITATIVE: 0057 boundary_certificate's four counts are
--             computed from it, and `mainline.permit.unmodelled_asset_count` is projected from
--             those counts by `fn_boundary_project` (band 0140-0149z).
-- sqlstate:   23514 on edge_kind_closed / from_tag_stated / to_tag_stated / no_self_asset_edge;
--             23505 on the primary key
-- exhibits:   spec R-3 (Exhibit Uniqueness) requires a refusal-bearing name to be unique across
--             the WHOLE schema, not merely within its table, because the exhibit name alone must
--             identify the refusal. `kind_closed` is already taken by `mainline.event` (0033) and
--             `no_self_edge` by `mainline.event_edge` (0034), so this file uses
--             `edge_kind_closed` and `no_self_asset_edge`.
-- forward-only; no .down.sql exists at or below the protected floor (DM-14). Under MR-5 there
--             is no .up.sql either.
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- THIS IS THE ONE MODELLED FACT IN THE BOUNDARY TRIO, AND IT IS THE ONE NOBODY SIGNS.
--
--   permit_boundary (0055)      what the crew DECLARED they isolated       — an assertion
--   asset_edge      (0054)      how energy and control actually flow       — a MODEL
--   permit_slice    (0056)      the backward slice over that model         — a COMPUTATION
--   boundary_certificate (0057) the arithmetic of the difference           — an EXHIBIT
--
-- The product's central move applied to physical isolation: a gate that read only the declared
-- boundary would be gating on the crew's own account of their own work. Reading the closure of
-- this graph instead is what lets `under_declared` accuse — the canonical multi-source-isolation
-- fatality, electrical locked out while trapped hydraulic pressure remains, is an asset in the
-- energy closure of the declared boundary that is absent FROM that boundary. Nobody has to
-- notice. The arithmetic notices.
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
-- THE FOUR EDGE KINDS, AND WHY THE VOCABULARY IS CLOSED.
--
--   energises      A supplies motive/electrical/pneumatic energy to B. The classic lockout edge.
--   stores_energy  A holds energy that can reach B after A's supply is isolated — accumulators,
--                  capacitor banks, raised loads, springs, trapped pressure, thermal mass. This
--                  is the edge whose ABSENCE kills people, because isolating the supply looks
--                  complete and the stored term is invisible on a single-line diagram.
--   governs        A controls or interlocks B: a PLC, a trip, an ESD, a permissive.
--   supersedes     A replaces B in a modernisation. Kept in the same graph, not a separate one,
--                  so a closure computed over the current asset register still reaches obsolete
--                  tags that older procedures name.
--
-- `edge_kind_closed` is a `CHECK IN (...)` rather than a lookup table because DM-11 draws that line at
-- "a writer OUTSIDE the schema supplies the value". The asset graph is loaded by the site's own
-- import path under `agent_gate`; nothing routes on this column, so a typo is a 23514 here and
-- never a silently dropped changefeed row.
--
-- WHY `no_self_asset_edge` IS A SAFETY CONSTRAINT AND NOT TIDINESS. `tags_unmodelled` (0057) counts
-- tags with NO EDGES AT ALL, and that count blocks the merge. A self-loop `('P-101','P-101')`
-- gives a tag an edge while conveying nothing about what it touches — so a single fat-fingered
-- row would move an asset from UNKNOWN to MODELLED and retire a refusal without adding one fact
-- about the plant. That is precisely the fail-open direction finding S11 was raised about, in
-- miniature and by accident. "This vessel stores energy" is a property of the vessel and belongs
-- in the site's asset register; "this vessel stores energy that can reach THAT flange" is an edge
-- and has two distinct endpoints. There is no third case.
--
-- WHY THE PRIMARY KEY INCLUDES `kind`. Two tags can stand in more than one relation at once — a
-- pump both energises a line and stores energy in it once the discharge valve shuts. Collapsing
-- them onto (site_id, from_tag, to_tag) would make the second insert a 23505 and would silently
-- keep whichever relation was loaded first, which is the more dangerous half of the pair exactly
-- half the time.
--
-- `site_id` IS THE PARTITION KEY AND IT IS NOT FOREIGN-KEYED, matching 0032, 0033 and the rest of
-- the vertical bands. Its authoritative source is `mainline.site` (DM-3) and the projection
-- triggers that read a site's scope token RAISE P0001 on a missing row; an FK here would add a
-- second, weaker copy of that rule and would put an ordering constraint on the corpus loader for
-- no gate that reads it. Stated rather than assumed, because "no FK" must be a decision.
--
-- INDEX `by_to`: THE CLOSURE IS WALKED BACKWARDS. The primary key covers "what does this tag
-- reach"; the certificate needs "what reaches this tag" — every source of energy that can arrive
-- at a declared boundary tag — and that walk is the one that finds the under-declared asset. Both
-- directions of a graph that is walked in both directions, declared inline per DM-6.
--
-- VERIFIED 2026-08-10 against CockroachDB CCL v26.2.5 (local single node, insecure, 26257). The
-- statement applies; a self-loop is refused with SQLSTATE 23514 and the server names `no_self_asset_edge`
-- in the CONSTRAINT field; an unknown `kind` is refused naming `edge_kind_closed`; and both relations
-- between one pair of tags coexist because `kind` is in the primary key. Evidence:
-- tests/integration/schema/test_mi_boundary_override.py, the `asset_edge` cases.

CREATE TABLE mainline.asset_edge (
  site_id  UUID   NOT NULL,   -- authoritative source: mainline.site (DM-3); no FK, see header
  from_tag STRING NOT NULL,
  to_tag   STRING NOT NULL,
  kind     STRING NOT NULL,
  CONSTRAINT asset_edge_pk PRIMARY KEY (site_id, from_tag, to_tag, kind),
  CONSTRAINT edge_kind_closed
    CHECK (kind IN ('energises', 'stores_energy', 'governs', 'supersedes')),
  CONSTRAINT from_tag_stated CHECK (from_tag <> ''),
  CONSTRAINT to_tag_stated CHECK (to_tag <> ''),
  -- A self-loop launders UNKNOWN into MODELLED without adding a fact. See the header.
  CONSTRAINT no_self_asset_edge CHECK (from_tag <> to_tag),
  INDEX by_to (site_id, to_tag, from_tag, kind)
);
