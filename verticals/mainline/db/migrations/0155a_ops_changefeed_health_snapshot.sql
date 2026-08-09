-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0155a_ops_changefeed_health_snapshot.sql
-- CREATE TABLE mainline_ops.changefeed_health_snapshot — the event spine, observable
--
-- MI: MI22
-- I: I06
-- COUNSEL-GATED: no
-- RATIONALE: A changefeed that has stopped is not a degraded feature; it is a blame
--            projection that stops being written, and MI22 says the gate fails closed on a
--            stale projection. The MCP identity cannot read SHOW CHANGEFEED JOBS or
--            crdb_internal.jobs, so the only way an auditor can ask "is the spine alive"
--            is a pre-materialised row with a highwater on it.
--
-- migration:  0155a_ops_changefeed_health_snapshot
-- domain:     datamodel / dm-views-rls
-- band:       0155-0169z · datamodel/dm-views-rls · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1). Suffixed onto
--             0155 as MR-5's multi-statement slot: one logical addition — the ops-family
--             source tables — that needs two CREATE TABLEs.
-- statements: 1
-- invariants: MI22 — the gate fails closed on a stale or absent projection. `highwater` and
--                    `behind_seconds` are the only honest way to say how stale.
--             I06  — the health of a dependency is COMPUTED and recorded, never declared.
-- source:     ARCHITECTURE.md §17 (the ops family: v_changefeed_health) · §8.5 (the
--             changefeed event spine, cf_outbox) · §9.1 (MCP limits) · §4.1 law 11
--             docs/leads/datamodel.md DM-16
-- requires:   0005 CREATE SCHEMA mainline_ops
-- sqlstate:   23514 on the named CHECKs; this table gates nothing.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHY A SINK URI IS STORED AS A DIGEST AND NOT AS TEXT
-- ─────────────────────────────────────────────────────────────────────────────
-- A changefeed sink URI carries its credentials inline — webhook bearer tokens,
-- S3 access keys, Kafka SASL passwords. `SHOW CHANGEFEED JOBS` redacts them;
-- crdb_internal.jobs does not always. A snapshot table read by an audit view
-- read by a Managed-MCP identity is the last place a credential should be able
-- to arrive, and "the collector redacts it" is a control that lives in code
-- somebody may edit. Storing SHA-256 of the URI keeps the property this table
-- actually needs — "is this the same sink as yesterday" is an equality test —
-- and makes the leak unrepresentable rather than merely unlikely.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHY CHANGEFEEDS ARE NOT MIGRATIONS, AND WHY THAT PUTS THE BURDEN HERE
-- ─────────────────────────────────────────────────────────────────────────────
-- §18: changefeeds are cluster jobs, re-created on restore, owned by the
-- provisioning agent — putting CREATE CHANGEFEED in a migration makes migrations
-- non-idempotent across environments and couples DDL to S3 credentials. The
-- consequence is that a restored cluster has the tables and none of the feeds,
-- and nothing in the schema knows. This table is where that gap becomes visible:
-- a feed absent from the newest snapshot is a feed nobody restarted.

CREATE TABLE mainline_ops.changefeed_health_snapshot (
  snapshot_id      UUID        NOT NULL DEFAULT gen_random_uuid(),
  collected_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  collector        STRING      NOT NULL,
  collector_ver    STRING      NOT NULL,
  -- The feed's stable name in the provisioning plan (cf_outbox, cf_register, …), NOT the
  -- job id: a job id changes on every restore, and "the feed changed" would then be true
  -- of every DR drill.
  feed_name        STRING      NOT NULL,
  job_status       STRING      NOT NULL,
  -- The resolved timestamp the feed has committed to. NULL means it has emitted no
  -- resolved span yet, which for a feed that has been running for an hour is the finding.
  highwater        TIMESTAMPTZ NULL,
  behind_seconds   FLOAT8      NULL,
  emitted_messages INT8        NOT NULL DEFAULT 0,
  -- Present iff job_status = 'failed'. Truncated by the collector; this is telemetry, not
  -- evidence, and an unbounded error string is how a 10 KiB response cap gets blown.
  error_text       STRING      NULL,
  sink_uri_sha256  BYTES       NOT NULL,
  sink_kind        STRING      NOT NULL,

  CONSTRAINT pk_changefeed_health_snapshot PRIMARY KEY (snapshot_id),
  CONSTRAINT changefeed_one_per_feed_per_run UNIQUE (collected_at, feed_name),
  CONSTRAINT changefeed_collector_stated     CHECK (collector <> ''),
  CONSTRAINT changefeed_collector_ver_stated CHECK (collector_ver <> ''),
  CONSTRAINT changefeed_feed_name_stated     CHECK (feed_name <> ''),
  CONSTRAINT changefeed_status_known
    CHECK (job_status IN ('running', 'paused', 'failed', 'canceled', 'succeeded', 'absent')),
  CONSTRAINT changefeed_sink_kind_known
    CHECK (sink_kind IN ('webhook', 'kafka', 'cloudstorage', 'pubsub', 'sinkless')),
  CONSTRAINT changefeed_sink_uri_is_sha256   CHECK (length(sink_uri_sha256) = 32),
  CONSTRAINT changefeed_emitted_nonneg       CHECK (emitted_messages >= 0),
  -- A feed cannot be behind by a negative amount. A negative lag is a clock problem on the
  -- collector, and a clock problem that presents as "healthier than possible" is the one
  -- direction of error an ops surface must never round away.
  CONSTRAINT changefeed_lag_nonneg           CHECK (behind_seconds IS NULL OR behind_seconds >= 0),
  -- An error text only means something against a failure. Attached to a running feed it is
  -- a stale string that outlives its cause, which is how an ops board grows a permanent red.
  CONSTRAINT changefeed_error_only_when_failed
    CHECK (error_text IS NULL OR job_status = 'failed'),
  -- 'absent' is the finding, not a gap: a feed the provisioning plan names and the cluster
  -- does not have must be a ROW saying so, because a missing row is indistinguishable from
  -- a collector that did not run.
  CONSTRAINT changefeed_absent_has_no_highwater
    CHECK (job_status <> 'absent' OR highwater IS NULL),
  INDEX changefeed_by_time (collected_at DESC, feed_name)
);
