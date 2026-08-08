-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI24
-- I: I04
-- COUNSEL-GATED: no
-- RATIONALE: COCKROACHDB HAS NO ADVISORY LOCKS, SO THE LEASE IS THE LOCK. One sequencer per site
-- is what keeps `seq` dense without a retry storm; this row is how that singleton is elected, and
-- a compare-and-swap on `epoch` under SERIALIZABLE is how the election is decided. It is the one
-- genuinely mutable object in the custody plane, and it is deliberately kept in `mainline_ops`
-- rather than `mainline` so that "everything in the ledger schema is append-only" stays a
-- sentence with no footnote.
--
-- migration:  0079_sequencer_lease
-- band:       0072-0079 · cu-ledger-ddl (custody) · see OWNERSHIP note in 0072
-- statements: 1
-- source:     ARCHITECTURE.md §5.6 (verbatim shape), §5.6 sequencer paragraph · §18 slot 0079 ·
--             §4.1 (no advisory locks) · docs/leads/custody.md worker 5 · docs/leads/
--             datamodel.md DM-13 (the same CAS shape is used by the migration lock table)
-- requires:   0006 CREATE SCHEMA mainline_ops · 0021 mainline.site
-- owes:       nothing. This table takes no append-only trigger, ON PURPOSE — see below.
-- grants:     `fk_site` requires `SELECT ON mainline.site` for `agent_sequencer` — see the
--             MEASURED PLATFORM FACT block in 0072.
-- sqlstate:   23503 on fk_site · 23505 on sequencer_lease_pkey · 23514 on the shape CHECKs
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- WHY THIS TABLE IS MUTABLE AND WHY THAT IS NOT A HOLE. It holds no evidence. Losing every row in
-- it costs one sequencing cycle: the next Lambda invocation finds no valid lease, takes one, and
-- carries on from `max(seq)` — which lives in `mainline.ledger_leaf`, where it is append-only and
-- CAS-protected. An adversary who rewrites this table can cause a duplicate sequencer to run;
-- the duplicate then collides on `ledger_leaf_pkey` and `ledger_linear` and loses. The lease is a
-- PERFORMANCE mechanism (avoid N-way contention), not a CORRECTNESS one, and saying so plainly is
-- what stops it being quietly relied upon as the latter. Correctness is the two constraints in
-- migration 0073, which hold at any isolation level and with no lease at all.
--
-- THE CAS SHAPE, stated so that every implementation of it matches:
--
--   UPDATE mainline_ops.sequencer_lease
--      SET holder = $new_holder, epoch = $observed_epoch + 1, expires_at = $now + $ttl
--    WHERE site_code = $1 AND epoch = $observed_epoch
--      AND (holder = $new_holder OR expires_at < $now);
--
-- Zero rows updated means somebody else holds it — that is the entire protocol. `epoch` is
-- monotone per site and is what makes a stale holder's write lose even if its clock is wrong:
-- a sequencer that sleeps through its own expiry and wakes up still believing it holds the lease
-- observes an epoch that has moved and updates nothing. The row is created once per site by the
-- provisioning path; there is no INSERT in the steady-state loop.
--
-- `epoch` IS NOT PRODUCED BY A SEQUENCE, and the reason is the same one that governs the whole
-- band: `CREATE SEQUENCE`, `nextval()`, `SERIAL` and `unique_rowid()` are banned repository-wide
-- and `trappoint migrate lint` refuses them in every migration and rendered template. Here the
-- derivation is `observed + 1` inside the CAS predicate, which is what makes the compare and the
-- swap one atomic step rather than two.
--
-- `expires_at` IS A LOCAL CLOCK AND THAT IS ACCEPTABLE HERE, uniquely in this band, because
-- nothing evidentiary reads it. A skewed clock costs an early or late failover, which the epoch
-- CAS then resolves correctly. Every other timestamp in the custody surface carries a warning
-- that it is not a time bound; this one genuinely is just a clock, and being explicit about the
-- difference is how the warnings elsewhere keep their force.
--
-- `fk_site` EXISTS BECAUSE A LEASE FOR A SITE NOBODY PROVISIONED IS A SEQUENCER RUNNING AGAINST A
-- TREE THAT SHOULD NOT EXIST. `mainline.site` is the authoritative source for every `site_code`
-- in the schema (migration 0021); a lease is the first thing created for a new site's ledger, so
-- it is exactly where a typo in a site code would otherwise take root and then propagate into
-- `ledger_intake` rows that look perfectly well-formed.
--
-- NO ROW-LEVEL TTL ON THIS TABLE, and it is the one place in this band where that needs a reason
-- other than evidence: an expired lease row must remain VISIBLE, because the recovery path reads
-- it to learn the epoch it must beat. A TTL would delete the row instead of expiring the lease,
-- and the next sequencer would find nothing, INSERT a fresh row at epoch 0, and hand the same
-- position to two writers. It would work in testing and fail under exactly the partition it was
-- meant to survive.

CREATE TABLE mainline_ops.sequencer_lease (
  site_code  STRING      NOT NULL,
  holder     STRING      NOT NULL,   -- Lambda request id / container id; opaque, compared only
  epoch      INT8        NOT NULL,   -- monotone per site; the CAS token. Never from a sequence
  expires_at TIMESTAMPTZ NOT NULL,   -- a genuine local clock; nothing evidentiary reads it
  CONSTRAINT sequencer_lease_pkey PRIMARY KEY (site_code),
  CONSTRAINT fk_site FOREIGN KEY (site_code) REFERENCES mainline.site (site_code),
  CONSTRAINT epoch_non_negative CHECK (epoch >= 0),
  CONSTRAINT holder_stated CHECK (holder <> '')
);
