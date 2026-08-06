-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- migration:  0046_event_bond
-- domain:     recall
-- statements: 1
-- invariants: MI16 — every severity-5 event bonded to the permit's activity node or an ancestor
--             is blocking. THIS is the table MI16 quantifies over.
-- source:     ARCHITECTURE.md §5.4 (channel B) · §6.4
-- requires:   0032 mainline.activity_node · 0033 mainline.event
-- sqlstate:   23503 on a bond to an unknown event or activity node
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- Channel B: "a fatality never decays" — STRUCTURALLY, not as a score hack. A score decay
-- constant that happens to be small is a tuning parameter, and a tuning parameter is something
-- a future engineer changes in a sprint. A bond is a row: every severity-5 event bonded to the
-- permit's activity node or any ancestor of it is a blocking obligation, unconditionally, with
-- no threshold, no calibration and no model call anywhere in the path.
--
-- `mainline.fn_bonded_sev5` (0113) reads this table on every blocking check that lands, and the
-- CHECK `bonded_fatalities_all_blocking` on `mainline_meas.recall_run` (0081) refuses any run
-- row whose two bonded counters disagree. That is MI16 enforced by the database rather than
-- asserted by the agent that would be the defendant.

CREATE TABLE mainline.event_bond (
  event_id     UUID   NOT NULL REFERENCES mainline.event (event_id),
  scope_id     UUID   NOT NULL REFERENCES mainline.activity_node (scope_id),
  taxonomy_ver INT4   NOT NULL,
  bond_basis   STRING NOT NULL CHECK (bond_basis IN ('coded','llm_induced','human')),
  CONSTRAINT event_bond_pk PRIMARY KEY (event_id, scope_id, taxonomy_ver),
  INDEX bond_by_scope (scope_id, taxonomy_ver, event_id)
);
