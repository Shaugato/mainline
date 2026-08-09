-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI22, MI26
-- I: I05
-- COUNSEL-GATED: no
-- RATIONALE: ORIGINDIFF — the delta of record is measured against the version the incident wrote, not against last week, and this view is the bounded query that says which version that was. It is a view and not a trigger because the merge gate's p99 is a product requirement and a recursive ancestry walk in a BEFORE INSERT is the classic way to lose it; it is driven off blame_edge and not off the version list because a clause carries single digits of blood and hundreds of retypesets, and the fan-out must be bounded by the former.
--
-- migration:  0152_v_blame_origin
-- domain:     algorithms
-- worker:     origin-diff (W6) — ORIGINDIFF
-- band:       0150-0154 · algorithms · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1), which grants
--             0150-0154 to the algorithms domain for `mainline.*` business views.
--             0150 is `v_safe_direction_current` (worker W2, DIRECTRIX) and 0151 is
--             `v_cbm_ledger` (worker W9, CBM LEDGER); this file takes the next free number in
--             the band. It was drafted at 0151 and moved when W9's file was found already on
--             disk at that number — MR-5's rule applies to a domain's own band as much as to a
--             neighbour's: a worker that finds its number taken takes the next one, it never
--             overwrites and it never suffixes into someone else's file. Recorded here rather
--             than corrected silently, because "two files at one number" is the exact failure
--             the reconciliation ruling exists to end, and `trappoint migrate lint` does NOT
--             catch it: rules A, B and C check a filename's SHAPE, its BAND and its SUFFIX, and
--             nothing in the lint compares two discovered files with each other.
-- statements: 1
-- invariants: I05  — ancestry monotone. This view is a read surface over the blame ancestry the
--                    BLOODLINE accumulator (M2) maintains; it computes nothing new about it.
--             MI22 — the gate fails closed on a stale or ABSENT blame projection. This view is
--                    what makes "absent" distinguishable from "clean": see THE LEFT JOIN IS THE
--                    POINT, below.
--             MI26 — the closure is append-only and generation-versioned, so a reader must take
--                    max(closure_gen). That discipline lives in `mainline.clause_blame_current`
--                    and this view reads it there rather than repeating it (DM-9).
-- source:     ARCHITECTURE.md §5.2 (commit_obj, commit_edge) · §5.3 (clause_version) ·
--             §5.4 (blame_edge, clause_blame_closure, clause_blame_current) · §3.3 M1/M2 ·
--             §3.2 I05/I06
--             docs/leads/algorithms.md D7, §2 ORIGINDIFF (written as 0212; RELOCATED to the
--             0150-0154 band by the migration reconciliation ruling of 2026-08-08 — the
--             0200-0219 annexe is revoked and lint rule B refuses any file that claims it)
--             research/05-architecture/clause-identity.md §5, last paragraph
-- requires:   0024 mainline.commit_obj · 0029 mainline.clause_version ·
--             mainline.blame_edge · mainline.clause_blame_closure ·
--             mainline.clause_blame_current · mainline.event
--             THE LAST FOUR ARE datamodel/dm-blame's (band 0032-0039z) AND HAD NOT LANDED WHEN
--             THIS FILE WAS WRITTEN. Only 0032-0036 are on disk. This view therefore cannot be
--             applied against the tree as it currently stands, and that is a real, stated
--             dependency and not a caveat: tests/integration/algorithms/diachronic reports
--             precisely which objects are missing and SKIPS rather than substituting a
--             hand-written twin, because a twin proves that the test file is self-consistent and
--             nothing else.
-- reads:      mainline.clause_blame_current ONLY — never mainline.clause_blame_closure directly.
--             DM-9 makes that view the sole read path so that max(closure_gen) is taken in one
--             place, and a CI grep fails a file that names the closure table.
-- sqlstate:   none — this object refuses nothing. It is a query, and the refusals it feeds are
--             the kernel's merge gate (MI02 / MI30) and worker W4's witness guard (P0001).
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- WHAT THIS VIEW ANSWERS
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- For every clause version (clause_uuid, commit_id), it answers: WHICH EARLIER VERSION OF THIS
-- CLAUSE DID THE INCIDENT WRITE?
--
-- Formally: the earliest-generation version of the clause at which an ACTIVE blame edge attached
-- carrying severity equal to the clause's current `clause_blame_current.max_severity`. Ties break
-- to the earliest generation and then to the lexicographically smallest `commit_id`.
--
-- That version is the baseline `mainline_domain.diachronic.ancestral_diff.delta_of_record` diffs
-- against, alongside the parent. Twenty individually-neutral commits whose composition weakens a
-- control are refused at commit twenty, because the comparison never had a parent to hide behind.
-- Every synchronic document-control system has exactly one baseline — the previous revision — and
-- cannot express this question at all.
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- THE LEFT JOIN IS THE POINT, AND IT IS NOT A STYLE CHOICE
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- Three states have to be distinguishable by a reader, and only two of them survive an inner
-- join:
--
--   NO ROW AT ALL          the clause has no `clause_blame_current` row: its blame closure has
--                          NOT BEEN PROJECTED. P2 forbids a gate from reading past an absent
--                          projection, so `resolve_origin` RAISES `BlameClosureAbsent` here.
--                          If this were reported as "no blood", DELETING THE PROJECTION would be
--                          the cheapest attack in the whole product — cheaper than rewording the
--                          clause, and invisible in the clause's own history.
--
--   ROW, ORIGIN COLUMNS    the closure was projected and is clean, or carries no ACTIVE edge at
--   NULL                   `max_severity`. The mechanism is INERT: the origin is the parent, the
--                          delta of record collapses to the ordinary parent diff, and a clause
--                          with no blood gets no louder. That last property is what keeps the
--                          nuisance ceiling (risk R-A7) in reach.
--
--   ROW, ORIGIN COLUMNS    the origin is resolved and the exhibit sentence is available.
--   POPULATED
--
-- The INNER join to `clause_blame_current` and the LEFT join to `blame_edge` are therefore doing
-- two different jobs: the first makes an unprojected closure disappear from the view entirely
-- (which is the signal), the second makes a projected-and-clean closure appear with empty origin
-- columns (which is the other signal).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- WHY IT IS DRIVEN OFF blame_edge AND NOT OFF THE VERSION LIST
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- The obvious formulation joins every earlier version of the clause and asks which of them
-- carries blood. On a nine-year-old procedure a clause has hundreds of versions and single digits
-- of blame edges, so that formulation's fan-out is bounded by how often the document was
-- RETYPESET — which is unrelated to anything and grows without limit.
--
-- Driving off `mainline.blame_edge` inverts it. `blame_edge`'s primary key leads with
-- `clause_uuid`, so the edges of one clause are a short primary-index range scan; each edge then
-- resolves to at most one version through `cv_clause_commit_unique (clause_uuid, commit_id)`,
-- which is a unique-index seek. The work is proportional to how much blood the clause carries.
--
-- THE EXPLICIT DEPTH BOUND `s.gen - o.gen <= 4096` is the belt to that braces. It is not a policy
-- about how far back blame reaches — 4096 generations is far more than a nine-year library
-- produces — it is what makes the statement's cost STATED rather than inferred, and it is
-- mirrored by `mainline_domain.diachronic.version.ORIGIN_DEPTH_BOUND`. The two copies are held
-- equal by tests/integration/algorithms/diachronic/test_v_blame_origin_shape.py, which parses
-- this file: two copies of a bound that can drift is a bound nobody can rely on.
--
-- The failure mode if the bound were ever reached is FAIL-OPEN (no origin row, mechanism inert,
-- quieter delta), which is why `origin_depth` is projected and why `BlameOrigin` carries
-- `depth_bound_reached`. A fail-open path that nobody can see is the one thing this design will
-- not ship.
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- NO RECURSION IN HERE, AND WHERE THE FIRST-PARENT WALK ACTUALLY LIVES
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- Ancestry in MAINLINE means FIRST-PARENT ancestry (`commit_edge.parent_ord = 0`). A merge commit
-- has two parents, and if an origin could be resolved through the second one, an author could
-- merge a bloodless branch and have the clause's origin quietly re-parent onto it.
--
-- That walk is NOT in this view, and the reason is arithmetic rather than taste: a recursive CTE
-- inside a view has no seed to be parameterised by, so it would enumerate the transitive closure
-- of every commit in the database and then filter — the exact opposite of bounded. So this view
-- returns the CONSERVATIVE candidate (the earliest blood-bearing version of the clause, from any
-- branch), and `mainline_domain.diachronic.origin.FIRST_PARENT_ANCESTRY_SQL` — one statement,
-- seeded at one commit, `parent_ord = 0` so the walk is a path and cannot fan out, with an
-- explicit depth bound in the recursive term — verifies chain membership afterwards.
--
-- A CANDIDATE THAT FAILS VERIFICATION IS KEPT, NOT DROPPED, AND THE DIRECTION IS THE WHOLE POINT.
-- Dropping it would mean an unverifiable chain produces a QUIETER delta, which is precisely what
-- the re-parenting merge was for. Keeping it can only raise the force of the delta of record
-- (the record is a join), so the worst case is an adjudication.
-- `BlameOrigin.first_parent_verified` is how the adjudicator learns why.
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- THREE ORDERING AND NULL DETAILS THAT ARE LOAD-BEARING
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- (a) `(o.commit_id IS NULL)` LEADS THE TIE-BREAK. CockroachDB sorts NULLs FIRST in ascending
--     order, where PostgreSQL sorts them last. Ordering on `o.gen` alone would therefore put the
--     LEFT-JOIN misses ahead of the real candidates on CockroachDB and behind them on
--     PostgreSQL, and `DISTINCT ON` would pick a different row on each. The boolean expression
--     makes the intent explicit and the answer identical on both.
-- (b) `o.commit_id` IS THE FINAL TIE-BREAK, so two versions of one clause at the same generation
--     — which history forks make possible, and which is exactly why `clause_version`'s primary
--     key carries `commit_id` as a third column — resolve deterministically. "The origin" appears
--     in an exhibit, and an exhibit that is not reproducible is not an exhibit.
-- (c) `origin_is_parent` IS COALESCED. `o.commit_id = s.parent_version` is NULL for a birth
--     version, and a three-valued boolean reaching a caller as "unknown" is a caller that will
--     eventually treat it as true.
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- WHAT THIS VIEW REFUSES TO LET A MODEL DO — INHERITED, NOT ADDED
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- `be.state = 'active'` carries two invariants this file does not have to restate:
--   MI13 — `inference_never_blocks` refuses an `inferred_semantic` edge in state `active`, so a
--          model's guess about which clause an incident wrote can never DEFINE a blame origin;
--   MI14 — `model_cannot_arm` refuses `severity_gate >= 4` on a `model_rated` basis, so a model's
--          severity can never be the `max_severity` this view matches on.
-- Both are CHECKs on the tables underneath. This view gets them for free by reading the columns
-- rather than re-deriving them, which is the point of P2.
--
-- ── `projected_sev_max` IS A DIAGNOSTIC AND IS NOT READ BY THE GATE ──────────────────────────
-- `clause_version.sev_max` is the P2 projection of the same quantity `clause_blame_current.
-- max_severity` holds. They must agree. Projecting both here makes a disagreement — a stale
-- BLOODLINE accumulator, a closure regenerated after the version row was written — visible to an
-- audit query instead of only to whoever eventually notices a delta that came out too quiet.
-- Nothing in `mainline_domain.diachronic` reads it, and nothing should start without deciding
-- first which of the two is authoritative.

CREATE VIEW mainline.v_blame_origin AS
SELECT DISTINCT ON (s.clause_uuid, s.commit_id)
       s.clause_uuid                                     AS clause_uuid,
       s.commit_id                                       AS as_of_commit,
       s.site_id                                         AS site_id,
       s.gen                                             AS as_of_gen,
       s.parent_version                                  AS parent_version,
       s.sev_max                                         AS projected_sev_max,
       cbc.max_severity                                  AS max_severity,
       cbc.closure_gen                                   AS closure_gen,
       cbc.truncated                                     AS closure_truncated,
       o.commit_id                                       AS origin_commit,
       o.gen                                             AS origin_gen,
       s.gen - o.gen                                     AS origin_depth,
       be.event_id                                       AS origin_event,
       ev.severity_gate                                  AS origin_severity,
       be.basis::STRING                                  AS origin_basis,
       COALESCE(o.commit_id = s.parent_version, false)   AS origin_is_parent
  FROM mainline.clause_version s
  -- INNER: a subject with no projected closure must not appear at all. That absence is the
  -- signal `resolve_origin` raises BlameClosureAbsent on (MI22 / P2).
  JOIN mainline.clause_blame_current cbc
    ON cbc.clause_uuid  = s.clause_uuid
   AND cbc.as_of_commit = s.commit_id
  -- LEFT: a projected-and-clean closure must appear WITH EMPTY origin columns, which is the
  -- inert case. `state = 'active'` inherits MI13 and MI14 (see above).
  LEFT JOIN mainline.blame_edge be
    ON be.clause_uuid = s.clause_uuid
   AND be.state       = 'active'::mainline.blame_state
   AND cbc.max_severity > 0
  LEFT JOIN mainline.event ev
    ON ev.event_id       = be.event_id
   AND ev.severity_gate  = cbc.max_severity
  -- At most one row per surviving edge: (clause_uuid, commit_id) is unique on clause_version.
  LEFT JOIN mainline.clause_version o
    ON o.clause_uuid  = s.clause_uuid
   AND o.commit_id    = be.commit_id
   AND ev.event_id   IS NOT NULL
   AND o.gen         <= s.gen
   AND s.gen - o.gen <= 4096
 ORDER BY s.clause_uuid,
          s.commit_id,
          (o.commit_id IS NULL),   -- real candidates first, on either engine's NULL ordering
          o.gen,                   -- earliest generation: the version the incident wrote
          o.commit_id;             -- and a deterministic tie-break when history forked
