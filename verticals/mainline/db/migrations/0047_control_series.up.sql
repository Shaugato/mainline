-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI19, MI01
-- I: I06
-- COUNSEL-GATED: no
-- RATIONALE: A CONTROL IS NOT A DOCUMENT. The Australian series system separates the thing that persists (the control) from the thing that carries it for a while (the document), which is what lets a procedure be rewritten, split, merged and renamed without any moment at which the obligation stops existing.
--
-- migration:  0047_control_series
-- band:       0024-0031, 0047-0049 · dm-spine
-- statements: 1
-- source:     ARCHITECTURE.md §5.3 (verbatim shape; constraints named per DM-10) · §16 MI19
--             · ISO 15489 / NAA functional classification
-- requires:   0024 mainline.commit_obj
-- projects:   nothing. This table is AUTHORITATIVE: mainline.carriage (0048) references it, and
--             mainline.doc.open_token_count (0027) is a count of carriage rows for series
--             declared here.
-- sqlstate:   23503 on fk_retired_commit; 23514 on criticality_closed / label_stated /
--             activity_root_stated; 23505 on control_series_label_unique
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- THE AUSTRALIAN SERIES SYSTEM, AND WHY AN ARCHIVAL IDEA IS LOAD-BEARING IN A SAFETY DATABASE.
-- Traditional records management binds a record to the agency that created it. The Australian
-- series system, developed at the Commonwealth Archives Office in the 1960s, breaks that binding:
-- the SERIES persists, and its relationships to agencies (who controlled it) and to other series
-- (what superseded it) are TIME-BOUNDED links recorded separately. Agencies get abolished,
-- amalgamated and renamed; the series survives all of it, with an unbroken chain of custody.
--
-- Substitute "document" for "agency" and the same structure solves the safety problem exactly.
-- An obligation — "isolate stored energy before intrusive work" — outlives every document that
-- ever states it. Procedures are rewritten every three years; a control written by a 2019
-- fatality has to survive nine rewrites, two mergers and a corporate rebrand without a single
-- moment where it is not somebody's responsibility. Binding the control to the document makes
-- rewriting the document a way to delete the control, silently, with nobody deciding anything.
-- So the control is a SERIES row here, and its residence in a document is a time-bounded CARRIAGE
-- row in 0048. That indirection is the whole mechanism behind MI19.
--
-- `label` IS THE HUMAN NAME AND IT IS UNIQUE PER SITE. It is what appears in the console, in a
-- disclosure bundle, and in the sentence a supervisor says out loud. `control_series_label_unique
-- (site_id, label)` means two people cannot be talking about different obligations while using
-- the same words. There is no global uniqueness: two sites may legitimately name their own
-- controls the same way, and forcing them apart would either mangle site vocabulary or make the
-- register a shared namespace nobody owns.
--
-- `criticality` IS DECLARED, NOT DERIVED, AND THAT IS DELIBERATE — READ THIS BEFORE USING IT.
-- 'critical' / 'major' / 'standard' is the customer's own classification of the control: their
-- critical-control register, their words, their governance. It is NOT `virulence`. Virulence is
-- banded from ANCESTRAL SEVERITY by a trigger over the blame closure and it is what the clearance
-- lattice keys on; nothing in the gate reads this column. The distinction is the product's
-- central claim in miniature: what a control is DECLARED to be is an assertion by whoever wrote
-- the register, and what a control WAS WRITTEN BY is a fact about ancestry. A gate that trusted
-- the declaration would be gating on the writer's opinion of their own change — which is exactly
-- the synchronic design every competitor ships. Keeping both, and never letting this one reach a
-- CHECK, is how the two stay distinguishable in evidence.
--
-- `activity_root` PLACES THE SERIES IN THE FUNCTIONAL TAXONOMY, the same axis used as the vector
-- prefix on 0031 and as the scope tree for the LMB cue entity. Functional classification is why
-- blame survives: asset tags and org charts churn every three years, "isolating stored energy
-- before intrusive work" does not.
--
-- `retired_commit` IS HOW A SERIES ENDS, AND IT ENDS BY AN ACT. Retiring a control is a decision
-- with an author, recorded as the commit in which that decision was made — never a DELETE, never
-- a NULLed row, never an absence. MI01 keeps this table append-only apart from that one pointer.
-- A retired series still holds every carriage it ever had, so "when did this obligation stop
-- being anyone's job, and who said so" is answerable years later.
--
-- NO SECONDARY INDEX. The two access patterns are by `series_id` (the primary key, from carriage)
-- and by `(site_id, label)` (the unique constraint, from the console and the register import).
-- Both are covered. An index on `(site_id, activity_root)` was considered and left out: the
-- register is small — hundreds of rows per site, not millions — and an unused index is a write
-- cost with no reader.
--
-- UNVERIFIED ON THIS MACHINE: no CockroachDB v26.2 was reachable when this band was authored, so
-- this statement has not been executed. See tests/integration/schema/test_mi_spine.py.

CREATE TABLE mainline.control_series (
  series_id      UUID   NOT NULL DEFAULT gen_random_uuid(),
  site_id        UUID   NOT NULL,
  activity_root  STRING NOT NULL,
  criticality    STRING NOT NULL,   -- the CUSTOMER's register. NOT virulence. Nothing gates on it.
  label          STRING NOT NULL,
  retired_commit BYTES  NULL,       -- retirement is an ACT, with an author and a commit
  CONSTRAINT control_series_pk PRIMARY KEY (series_id),
  CONSTRAINT control_series_label_unique UNIQUE (site_id, label),
  CONSTRAINT fk_retired_commit FOREIGN KEY (retired_commit)
    REFERENCES mainline.commit_obj (commit_id),
  CONSTRAINT criticality_closed CHECK (criticality IN ('critical', 'major', 'standard')),
  CONSTRAINT label_stated CHECK (label <> ''),
  CONSTRAINT activity_root_stated CHECK (activity_root <> '')
);
