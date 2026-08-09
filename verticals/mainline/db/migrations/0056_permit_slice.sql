-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI06, MI17
-- I: I06
-- COUNSEL-GATED: no
-- RATIONALE: The backward slice is the COMPUTED half of I06 and it does two jobs. It BOUNDS which clauses may raise a blocking check against this permit, which turns alarm fatigue from a complaint into a set with an argument and gives every rate MAINLINE quotes a published denominator; and its COMPLEMENT accuses, because an asset in the energy closure of the declared boundary and absent from that boundary is the multi-source isolation failure. A declared cohort would do neither: it would be the crew's opinion of their own exposure.
--
-- migration:  0056_permit_slice
-- band:       0054-0057z · datamodel/ex-dm-gate · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- statements: 1
-- source:     ARCHITECTURE.md §5.5 (shape verbatim; two constraints and one index added, each
--             justified below) · finding S11 · §16 MI06, MI17 · §4.1 I06
-- requires:   0050 mainline.permit (RENDERED) · 0028 mainline.clause (AUTHORED, dm-spine)
-- projects:   nothing. AUTHORITATIVE: `fn_drift_to_check` (band 0140-0149z) reads this table to
--             decide which open subjects a drift finding raises a check against, and every
--             coverage rate published by the console is a fraction whose denominator is a count
--             of rows here.
-- sqlstate:   23503 on fk_slice_permit / fk_slice_clause; 23514 on slice_hop_nonneg /
--             slice_hop_is_traceable / via_asset_stated; 23505 on the primary key
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- ONE ROW PER (permit, clause). `hop` IS THE SHORTEST DISTANCE, NOT A PATH ENUMERATION.
--
-- The primary key (permit_id, clause_uuid) is from §5.5 and it is the right shape, but it has a
-- consequence worth stating where the writer will read it: this table cannot hold two routes to
-- the same clause. `hop` is therefore the MINIMUM number of asset-graph edges between the
-- declared boundary and the clause, and `via_asset` is the asset on THAT route. A slice writer
-- that inserts routes as it finds them will produce a 23505 on the second route and must
-- `ON CONFLICT DO UPDATE ... WHERE excluded.hop < permit_slice.hop`, or compute the minimum
-- before writing. Recording every route instead would multiply the denominator by the
-- connectivity of the plant and make every published rate meaningless.
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
-- THE TWO JOBS, IN THE ORDER THEY MATTER.
--
-- 1. IT BOUNDS. A blocking check exists against a permit because a clause in that permit's slice
--    carries blame ancestry. Without the slice the candidate set is "every clause at the site",
--    every permit inherits every precursor, and the product becomes the alarm flood it exists to
--    replace. The slice is the argument for why a clause was NOT raised — which is the half of a
--    recall claim that is normally unfalsifiable and here is a stored set.
-- 2. ITS COMPLEMENT ACCUSES. `under_declared` in 0057 counts assets reachable in the energy
--    closure that never appear in `permit_boundary`. The slice is how that closure is recorded,
--    so the accusation is arithmetic over two tables rather than a judgement by a reviewer.
--
-- WHY `fk_slice_clause` IS ADDED AND `permit_boundary` HAS NO EQUIVALENT (0055). The asymmetry is
-- the point and it is not an oversight. An UNMODELLED ASSET TAG MUST BE WRITEABLE, because
-- counting it is what blocks the merge (see 0055's header). A PHANTOM CLAUSE has the opposite
-- polarity: a slice row naming a clause_uuid that does not exist inflates the denominator of
-- every published coverage rate with a member nothing can ever be true of, and no refusal
-- anywhere depends on it being writeable. Where a missing row is the evidence, admit it; where a
-- missing row is only ever an error, refuse it. `mainline.clause` and not `clause_version`
-- because the slice is over clause IDENTITY: a clause is in the exposed cohort whatever version
-- of it the permit happens to cite, and pinning the version here would make a slice go stale on
-- an edit that did not change the plant.
--
-- `slice_hop_is_traceable` — a non-zero hop must name the asset it came through. hop = 0 is "the
-- permit cites this clause directly"; hop >= 1 is "the asset graph put it in scope", and a row
-- claiming the second without naming the asset is an accusation with no chain of reasoning
-- attached, which is exactly the sort of exhibit that collapses under cross-examination. The
-- CONVERSE is deliberately left open: a hop-0 row MAY carry a `via_asset` (the clause governs a
-- declared boundary tag directly), and forbidding that would refuse a true row to make a
-- constraint symmetrical.
--
-- NO UPPER BOUND ON `hop`. The closure's depth limit is a parameter of the computation, not a
-- fact about the schema, and a schema-level ceiling would silently truncate a slice on the day a
-- site models its plant more finely than the number someone typed here.
--
-- INDEX `by_clause`: the reverse lookup is a first-class read path, not a report. When a drift
-- finding lands on a clause, `fn_drift_to_check` must find every OPEN subject whose slice
-- contains it; the primary key answers "what is in this permit's slice" and cannot answer "which
-- permits contain this clause". Declared inline per DM-6.
--
-- VERIFIED 2026-08-10 against CockroachDB CCL v26.2.5 (local single node, insecure, 26257). The
-- statement applies; `hop = 2` with a NULL `via_asset` is refused with 23514 naming
-- `slice_hop_is_traceable`; and a slice row naming a clause_uuid with no `mainline.clause` row is
-- refused with 23503 naming `fk_slice_clause`. Evidence:
-- tests/integration/schema/test_mi_boundary_override.py, the `permit_slice` cases.

CREATE TABLE mainline.permit_slice (
  permit_id   UUID   NOT NULL,
  clause_uuid UUID   NOT NULL,
  hop         INT2   NOT NULL,   -- SHORTEST distance in asset-graph edges. See the header.
  via_asset   STRING NULL,       -- the asset on that shortest route; NULL only when hop = 0
  CONSTRAINT permit_slice_pk PRIMARY KEY (permit_id, clause_uuid),
  CONSTRAINT fk_slice_permit FOREIGN KEY (permit_id)
    REFERENCES mainline.permit (permit_id)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT fk_slice_clause FOREIGN KEY (clause_uuid)
    REFERENCES mainline.clause (clause_uuid)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT slice_hop_nonneg CHECK (hop >= 0),
  CONSTRAINT slice_hop_is_traceable CHECK (hop = 0 OR via_asset IS NOT NULL),
  CONSTRAINT via_asset_stated CHECK (via_asset IS NULL OR via_asset <> ''),
  INDEX by_clause (clause_uuid, permit_id)
);
