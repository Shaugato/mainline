-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0049c_cbm_account.sql
-- CREATE TABLE mainline.cbm_account — CONSERVATION OF BLAME MASS, as arithmetic the
-- database refuses to be wrong about
--
-- MI: MI03, MI25, MI26
-- I: I02, I05
-- COUNSEL-GATED: no
-- RATIONALE: `identity_residue` already gives an undispositioned residue row a merge refusal
--            (MI03). What nothing gives is a guarantee that residue EMISSION WAS COMPLETE — a
--            matcher that quietly under-emits produces a clean gate, and the flagship claim is
--            then only as strong as the code that wrote the rows. This table closes that by
--            storing the conservation identity itself and making it a plain-column CHECK over a
--            STORED generated column: `inherited = carried + split_carried + merge_carried +
--            residue_open + residue_disposed`. Five obligations in and four out is `23514` at
--            the moment of accounting, for every writer, forever — not a report, not a metric,
--            not a nightly job. The counters are then re-derived by `fn_cbm_account_guard`
--            (0140a) from the authoritative relations and OVERWRITE whatever the inserter
--            supplied, because a projector that can choose its own numerator is not a
--            projection (P2, and finding S1 applied to the accounting rather than to severity).
--
-- migration:  0049c_cbm_account
-- domain:     algorithms
-- band:       0049a-0049z · algorithms · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1). The algorithms
--             table annexe is granted to this domain explicitly and exclusively; `0049a` is
--             `delta_witness` (W4) and `0049b` is reserved for W8's `identity_assignment`,
--             which a reader will find named in this file's `requires:` line.
-- statements: 1  (the CREATE TABLE, and nothing else)
-- invariants: MI03 — a merged subject carries zero un-dispositioned identity residue. This
--                    table is the arithmetic BEHIND that count, one level down: MI03 refuses a
--                    residue row that is open; `cbm_balances` refuses a residue row that was
--                    never written.
--             MI25 — a gate column is a projection of the blame closure and never an input.
--                    Every counter here is re-derived by 0140a from `clause_blame_current`,
--                    `identity_assignment` and `identity_residue`.
--             MI26 — append-only and generation-versioned, exactly as the closure is. A
--                    correction is a NEW generation, never an edit.
--             I02  — projected refusal. I05 — the generation guard is monotone.
-- source:     docs/leads/algorithms.md §5 (PROJECT / REFUSE structural / REFUSE gate) · §2
--             CBM LEDGER · ARCHITECTURE.md §5.3 identity_residue · §5.4 clause_blame_closure /
--             clause_blame_current · §16 MI03/MI25/MI26 · §3.1 PROJECT-PIN-REFUSE.
--             Written in the brief as `0201_cbm_account.sql`; `0200`+ is UNALLOCATED (MR-7)
--             and `trappoint migrate lint` rule B refuses it, so the object takes a number
--             from this domain's own table annexe.
-- requires:   0024 mainline.commit_obj (the FK target)
--             — and, before 0140a can be created, 0049 mainline.identity_residue,
--               0049b mainline.identity_assignment (W8) and mainline.clause_blame_current
--               (dm-blame, band 0032-0039). This CREATE TABLE needs none of them; the GUARD
--               does, and its header says so.
-- sqlstate:   23514 on cbm_balances / counts_nonneg / gen_nonneg / commit_id_is_sha256 /
--             projector_ver_stated; 23503 on fk_commit; 23505 on the primary key.
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- THE CONSERVATION LAW, AND WHY IT IS A COLUMN
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- Every ancestor clause carrying a blame edge to a severity ≥ 4 event is, in commit `c`, one of
-- exactly three things: MATCHED, matched THROUGH A RECORDED SPLIT OR MERGE, or EXPLICITLY
-- ABSENT with a signed disposition. There is no fourth state. Written as arithmetic:
--
--     inherited = carried + split_carried + merge_carried + residue_open + residue_disposed
--
-- The left side is a fact about the PAST — how many blood-bearing obligations this commit
-- inherited. The right side is a fact about the PRESENT — what the matcher says happened to
-- each of them. A matcher that evades an obligation makes the right side smaller than the left,
-- and the row cannot be stored.
--
-- The five right-hand terms partition the ancestor set; they do not merely count rows. One
-- ancestor may produce several `identity_residue` rows (its UNIQUE key is (commit_id,
-- ancestor_clause_uuid, REASON) — a clause can be both `ambiguous` and `anchor_drop`), and one
-- ancestor may produce several `identity_assignment` rows under a split. Counting rows would
-- double-count and the identity would be arithmetic about nothing. 0140a therefore classifies
-- each ancestor into exactly ONE bucket under a fixed precedence, and that precedence is
-- fail-closed at every step:
--
--     residue_open  ≻  residue_disposed  ≻  split_carried  ≻  merge_carried  ≻  carried
--
-- An ancestor with BOTH a claimed match and an open residue row counts as residue_open, which
-- blocks. The generous reading is never the one taken.
--
-- ── WHY `balanced` IS A STORED COLUMN AND NOT AN INLINE CHECK EXPRESSION ─────────────────────
-- Both forms refuse the same writes. The stored column additionally makes the verdict
-- SELECTABLE and INDEXABLE — `mainline_audit.v_cbm_ledger` (0151) reports it, and a reader can
-- ask "which accounts balance" without re-deriving the sum in the query and getting it subtly
-- different. It is a tautology by construction (`cbm_balances` refuses `false`), and the audit
-- view says so rather than presenting it as news.
--
-- MEASURED, v26.2.5, and load-bearing for the exhibit: the `23514` MESSAGE names the CHECK
-- EXPRESSION, not the constraint — `failed to satisfy CHECK constraint (balanced)`. The
-- constraint NAME arrives in the error's diagnostics field (`PG:constraint_name` =
-- `cbm_balances`), which is where `tests/integration/algorithms/cbm/test_balance_refusal.py`
-- reads it. Any console or exhibit that promises an operator a constraint name for a 23514 must
-- take it from the diagnostics; the message alone will not carry it.
--
-- ── APPEND-ONLY AND GENERATION-VERSIONED, LIKE THE CLOSURE ───────────────────────────────────
-- `PRIMARY KEY (site_id, commit_id, account_gen)`. Re-accounting a commit writes a NEW row at
-- `account_gen + 1`; nothing is ever edited. This matters more here than it looks: the whole
-- attack this table exists to catch is "the accounting was right when it was written and the
-- world moved underneath it", and a table that could be updated in place would erase the
-- evidence of exactly that. 0140a enforces density and monotonicity of `account_gen` the way
-- `fn_closure_guard` does for the closure (MI26).
--
-- ── `site_id` IS PROJECTED, NOT SUPPLIED, AND THAT IS NOT PEDANTRY ───────────────────────────
-- A writer who chose `site_id` could write a commit's accounting under a site whose auditors
-- never look, and RLS would then hide the account from the people it indicts. 0140a re-derives
-- it from `mainline.commit_obj` and RAISEs when the commit does not exist. The FK below would
-- also catch a fabricated commit, but a FOREIGN KEY refuses an unknown commit; it does not
-- refuse a KNOWN commit filed under the wrong site.
--
-- ── `wrote_as` IS THE DATABASE'S ANSWER TO `computed_by`'S CLAIM ─────────────────────────────
-- `computed_by` is what the projector says it is — a Lambda name, a task ARN, a service tag —
-- and it is worth keeping because it is the operational handle. `wrote_as` is `current_user` as
-- the cluster saw it, written by the trigger. Two columns because they answer two questions,
-- and a disagreement between them is a finding rather than a mystery.
--
-- ── NO ON DELETE CASCADE. NO TTL. NO DELETE PATH AT ALL ──────────────────────────────────────
-- The FK onto `commit_obj` is RESTRICT in both directions. A cascade would let deleting a
-- commit erase the arithmetic that proves an obligation went missing from it, which is the
-- single most useful row in a post-incident reconstruction and the precise offence this
-- substrate exists to detect.
--
-- ── WHAT THIS TABLE DOES NOT DO ──────────────────────────────────────────────────────────────
-- It does not decide whether the matcher was RIGHT. `inherited` counts obligations; it says
-- nothing about whether `carried` matched them to the correct descendant clause. Blame landing
-- on the WRONG clause (risk R-A2) is not caught here and is not claimed to be — the escalation
-- ladder for that is in docs/leads/algorithms.md §8, and `novelty/cbm-ledger.yaml` records it
-- under `unverified`. CBM makes an obligation impossible to LOSE. It cannot make a match true.
--
-- ── UNVERIFIED / VERIFIED, STATED PRECISELY ──────────────────────────────────────────────────
-- The constructs in this statement were executed against CockroachDB CCL v26.2.5 on 2026-08-09:
-- `BOOL AS (...) STORED` with a `CHECK` over the generated column, the descending secondary
-- index with `STORING`, and the composite primary key all applied, and an under-emitted insert
-- returned `23514` with `constraint_name = cbm_balances`. What is NOT verified from this
-- machine is the table's behaviour under RLS: the write policy for `agent_projector` is
-- `dm-views-rls`'s file in band 0180-0198 and is not this domain's to write.

CREATE TABLE mainline.cbm_account (
  -- ▼▼ PROJECTED. Trigger-written by 0140a, never supplied. ▼▼
  site_id          UUID   NOT NULL,          -- from mainline.commit_obj.site_id (P2)
  -- ▲▲
  commit_id        BYTES  NOT NULL,
  account_gen      INT8   NOT NULL,          -- monotone, dense, per (site_id, commit_id)

  -- ▼▼ THE CONSERVATION IDENTITY. Every one of these six is re-derived by 0140a from
  --    clause_blame_current / identity_assignment / identity_residue and OVERWRITES whatever
  --    the inserter supplied. A value a client sends does not survive the write (I02). ▼▼
  inherited        INT8   NOT NULL,          -- |A(c)| : blood-bearing ancestors, sev >= 4
  carried          INT8   NOT NULL,          -- relation 'matched'
  split_carried    INT8   NOT NULL,          -- relation 'split'
  merge_carried    INT8   NOT NULL,          -- relation 'merge'
  residue_open     INT8   NOT NULL,          -- residue with disposition_id IS NULL  ⇒ blocking
  residue_disposed INT8   NOT NULL,          -- residue, every row dispositioned
  -- ▲▲

  computed_by      STRING NOT NULL,          -- the projector's CLAIM about its own identity
  wrote_as         NAME   NOT NULL,          -- current_user, as the cluster saw it (projected)
  projector_ver    STRING NOT NULL,          -- mainline_domain.cbm.version.PROJECTOR_VERSION
  computed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

  -- THE PRODUCT. A tautology by construction, and that IS the product: the only accounts that
  -- exist are the ones that balance.
  balanced         BOOL AS (
                     inherited = carried + split_carried + merge_carried
                                 + residue_open + residue_disposed
                   ) STORED,

  CONSTRAINT cbm_balances CHECK (balanced),

  CONSTRAINT counts_nonneg CHECK (
    inherited >= 0 AND
    carried >= 0 AND
    split_carried >= 0 AND
    merge_carried >= 0 AND
    residue_open >= 0 AND
    residue_disposed >= 0
  ),
  CONSTRAINT gen_nonneg           CHECK (account_gen >= 0),
  CONSTRAINT commit_id_is_sha256  CHECK (length(commit_id) = 32),
  CONSTRAINT computed_by_stated   CHECK (computed_by <> ''),
  CONSTRAINT projector_ver_stated CHECK (projector_ver <> ''),
  CONSTRAINT wrote_as_stated      CHECK (wrote_as <> ''),

  CONSTRAINT cbm_account_pk PRIMARY KEY (site_id, commit_id, account_gen),
  CONSTRAINT fk_commit FOREIGN KEY (commit_id) REFERENCES mainline.commit_obj (commit_id)
    ON UPDATE RESTRICT ON DELETE RESTRICT,

  -- The gate's own index. `z_cbm_gate` (0145c/0145d) asks one question per cited commit —
  -- "is there an account, and what did its newest generation say about open residue" — on the
  -- latency-critical merge path, and a descending generation answers it with a seek.
  INDEX cbm_by_commit (commit_id, account_gen DESC) STORING (residue_open, inherited)
);
