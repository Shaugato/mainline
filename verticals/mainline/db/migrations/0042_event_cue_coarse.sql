-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- migration:  0042_event_cue_coarse
-- domain:     recall
-- statements: 1
-- invariants: MI16 (the sweep's blocking rule reads `severity_gate`), MI25 (projection principle)
-- source:     ARCHITECTURE.md §5.4 (S20) · docs/leads/recall.md D1
-- requires:   0040 mainline.event_cue · 0033 mainline.event
-- sqlstate:   P0001 via 0114/0138 when the parent cue is absent
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- SIDECAR 2 — the taxonomy-insurance sweep. ONE tree, deliberately. A constant prefix column
-- buys nothing for partitioning, and that is exactly what this table wants: one big
-- unpartitioned K-means tree, so an event the induced taxonomy MISCLASSIFIED is still
-- reachable. Without it, a mis-taxonomised severity-4 event at one site is invisible to another
-- site's permit forever — by the design's own words.
--
-- `severity_gate` is denormalised here because it is the sweep's blocking rule: a sweep hit is
-- never blocking unless `severity_gate = 5`. A denormalised column that decides whether a
-- fatality blocks a permit is precisely the column an inserter must not be able to write, so it
-- is PROJECTED from `mainline.event` by `mainline.fn_cue_prefix_project` (0114) through
-- `event_cue.event_id`, and a missing parent cue RAISEs P0001.
--
-- `tenant_id` is CONSTANT for the deployment and is NOT projected by this domain's trigger:
-- DM-3 makes `mainline.site` the authoritative source for the tenant/site tokens. Until that
-- projection lands, `tenant_id` is a client-supplied constant — recorded here as an unclosed
-- weld rather than claimed as enforced.

CREATE TABLE mainline.event_cue_coarse (
  cue_id        UUID   NOT NULL REFERENCES mainline.event_cue (cue_id),
  tenant_id     UUID   NOT NULL,                -- CONSTANT for the deployment. One K-means tree.
  severity_gate INT2   NOT NULL,                -- the sweep's blocking rule  ← PROJECTED (0114)
  embed_model   STRING NOT NULL,
  index_gen     STRING NOT NULL,
  emb_coarse    VECTOR(256) NOT NULL,           -- 256-d, renormalised client-side
  CONSTRAINT event_cue_coarse_pk PRIMARY KEY (cue_id),
  CONSTRAINT coarse_sev_range CHECK (severity_gate BETWEEN 0 AND 5),
  VECTOR INDEX cue_sweep_idx (tenant_id, emb_coarse vector_cosine_ops)
);
