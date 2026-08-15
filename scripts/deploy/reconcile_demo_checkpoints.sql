-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: Apache-2.0
--
-- ══════════════════════════════════════════════════════════════════════════════════════════════
--  MAINLINE · reconcile_demo_checkpoints.sql — retire the self-naming checkpoint
--  owner:    demo-story / W6
--  target:   database `mainline_demo`, after the chain and after both demo seeds
--  applied:  by the ORCHESTRATOR. This file is applied to AWS by nobody else, and the worker
--            that wrote it applied it only to a local database of its own.
--  proved:   scripts/deploy/verify_demo_checkpoints.py  (before/after, on a local cluster)
--  recorded: docs/decisions/custody-stale-checkpoint.md
-- ══════════════════════════════════════════════════════════════════════════════════════════════
--
--  WHAT IS WRONG, MEASURED RATHER THAN ASSERTED
--
--  The custody surface reports `verification FAILED` on the seeded site, with four red checks.
--  Two of them — check 2 `inclusion_proof` and check 3 `consistency_proof_every_pair` — are one
--  row:
--
--    * `mainline.ledger_checkpoint` carries a row at `tree_size = 1` whose `root_hash` is
--      `digest('mainline-demo/ledger/root/1', 'sha256')` = `74f0845f11c5992b…` — the SHA-256 of
--      a STRING NAMING ITSELF, committing to nothing.
--    * The RFC 6962 Merkle Tree Hash of the first leaf the appender actually wrote is
--      `032980be3a0d1fb7…`. For a tree of size 1, MTH(D[0..1]) IS the leaf hash, so the
--      inclusion proof for `seq 0` against `tree_size 1` is the empty path and the recomputation
--      is unambiguous: `032980be…` against a recorded `74f0845f…`.
--    * The `1 → 2` consistency proof is anchored on the same fiction and disagrees for the same
--      reason.
--
--  Every size-2 and size-4 path AGREES: `bf5dc3e5…` IS node (1,0) and `49b22526…` IS node (2,0),
--  both read back out of `mainline.ledger_node`. The verifier is not wrong about anything. It is
--  working perfectly on a row that should not be there.
--
--  WHY THE ROW IS STILL THERE
--
--  `verticals/mainline/db/seeds/demo/demo_world.sql` §8 seeded exactly that checkpoint until
--  2026-08-14, over a `mainline.ledger_leaf` that held zero rows. The file now seeds `tree_size`
--  2 and 4 and reads both roots back out of `mainline.ledger_node`. But every insert in §8 is
--  guarded by `ON CONFLICT DO NOTHING` / `WHERE NOT EXISTS` and nothing in the chain has ever
--  deleted anything, so removing the statement removed the row from every database seeded from
--  scratch afterwards and from NO database that already held it. The deployed `mainline_demo`
--  kept it and served it.
--
--  WHAT THIS FILE MAY DELETE, STATED AS A PREDICATE RATHER THAN AS AN INTENTION
--
--  Three conjuncts, and each one is load-bearing:
--
--    1. `root_hash = digest('mainline-demo/ledger/root/' || tree_size, 'sha256')` — the
--       signature of the defect. A root that is the hash of its own name.
--    2. `NOT EXISTS (a node in mainline.ledger_node carrying that hash)` — the clause that makes
--       this safe to run for ever. A checkpoint whose root is a node the appender built is a
--       checkpoint over real leaves, and no such row can match, whatever it is numbered.
--    3. `EXISTS (an admissible, cosigned checkpoint at the same site at a LARGER tree_size)` —
--       the clause that protects every anchor the deleted row could have satisfied.
--       `mainline.fn_recall_policy_anchored` (migration 0112) asks whether some admissible,
--       cosigned checkpoint has `tree_size >= anchored_size`; any anchor this row answered has
--       `anchored_size <= cp.tree_size`, so a survivor strictly above it answers the same anchor
--       and every other one. "Larger" rather than "at least as large" because
--       `(site_code, tree_size)` is the primary key: no second row can sit at this one's size.
--       Measured — with checkpoints 2 and 4 removed first, so the self-naming row is the site's
--       only one, this file deletes NOTHING and the anchor survives.
--
--  There is NO `tree_size = 1` literal, no blanket `DELETE`, and no `WHERE` that widens if the
--  demo grows a fifth leaf. On a database that never carried the defect — every fresh apply —
--  both statements delete zero rows. That is what makes this idempotent, and it is why running
--  it twice is not a different operation from running it once.
--
--  THE SEED CARRIES AN EQUIVALENT STATEMENT, AND THAT IS NOT A REASON TO SKIP THIS ONE.
--
--  `demo_world.sql` §8.4 was given the same first two conjuncts on 2026-08-15. This file exists
--  anyway, for two reasons that are about deployment rather than about SQL. First, the seed is
--  applied by `seed_demo.py` and a database can be reconciled without re-seeding it — the
--  orchestrator may want the one statement and not the whole corpus. Second, this file carries
--  the THIRD conjunct, so it is strictly narrower than §8.4: it will not delete the row that is
--  holding a recall policy's anchor up, whatever else is true. Applying both changes nothing
--  twice: each is a no-op on a database the other has already reconciled.
--
--  ORDER, AND WHY IT IS NOT A STYLE CHOICE. `mainline.cosignature` has
--  `FOREIGN KEY (site_code, tree_size) REFERENCES mainline.ledger_checkpoint` (migration 0076),
--  so deleting the checkpoint under a live cosignature is `23503` and aborts the batch. The
--  cosignature goes first, narrowed by the SAME predicate re-stated against the checkpoint it
--  belongs to, so it can never reach a cosignature over a checkpoint this file is keeping.
--
--  NO `BEGIN` / `COMMIT`. This file is applied the way the seed files are — one statement batch
--  on `cloud_chain.Applier`'s autocommit connection, which makes the batch ONE implicit
--  transaction that CockroachDB can restart server-side on `40001`. An explicit transaction here
--  would take that recovery away and buy nothing: the two statements are already atomic together
--  under the batch.
--
--  WHAT THIS FILE DOES NOT FIX, AND WILL NOT PRETEND TO
--
--  Check 4 `log_signature` stays red after this runs. The seeded checkpoint note is
--  `mainline/<site>` / `<size>` / `<root>` with no empty line, so it has no signature section at
--  all — a true fact about a synthetic corpus, routed to `DEMO-HONESTY.md` §3 STAGED and stated
--  in `docs/decisions/custody-stale-checkpoint.md`. Nobody forges a signature to close it.
--  Check 10 `canonicaliser_identity` is likewise untouched by this file and is attributed in the
--  same document. No check is weakened, skipped or exempted here or anywhere else.
--
-- ──────────────────────────────────────────────────────────────────────────────────────────────

-- 1 · THE COSIGNATURE OVER THE SELF-NAMING CHECKPOINT
--
-- Narrowed by the checkpoint's own predicate, re-stated. A cosignature over a checkpoint this
-- file keeps cannot satisfy it.

DELETE FROM mainline.cosignature AS c
 WHERE c.site_code = 'dec0de00-0001-4000-8000-000000000001'
   AND EXISTS (
     SELECT 1
       FROM mainline.ledger_checkpoint AS cp
      WHERE cp.site_code = c.site_code
        AND cp.tree_size = c.tree_size
        AND cp.root_hash = digest('mainline-demo/ledger/root/' || cp.tree_size::STRING, 'sha256')
        AND NOT EXISTS (
          SELECT 1 FROM mainline.ledger_node AS n
           WHERE n.site_code = cp.site_code AND n.hash = cp.root_hash
        )
        AND EXISTS (
          SELECT 1
            FROM mainline.ledger_checkpoint AS keep
            JOIN mainline.cosignature AS ks
              ON ks.site_code = keep.site_code AND ks.tree_size = keep.tree_size
           WHERE keep.site_code = cp.site_code
             AND keep.tree_size > cp.tree_size
             AND keep.admissible
        )
   );

-- 2 · THE CHECKPOINT ITSELF
--
-- The same three conjuncts, stated once more against the row being removed. The third one is
-- evaluated AFTER statement 1 has run, and it still holds: statement 1 removed only the
-- cosignature over THIS checkpoint, never one over a checkpoint that survives.

DELETE FROM mainline.ledger_checkpoint AS cp
 WHERE cp.site_code = 'dec0de00-0001-4000-8000-000000000001'
   AND cp.root_hash = digest('mainline-demo/ledger/root/' || cp.tree_size::STRING, 'sha256')
   AND NOT EXISTS (
     SELECT 1 FROM mainline.ledger_node AS n
      WHERE n.site_code = cp.site_code AND n.hash = cp.root_hash
   )
   AND EXISTS (
     SELECT 1
       FROM mainline.ledger_checkpoint AS keep
       JOIN mainline.cosignature AS ks
         ON ks.site_code = keep.site_code AND ks.tree_size = keep.tree_size
      WHERE keep.site_code = cp.site_code
        AND keep.tree_size > cp.tree_size
        AND keep.admissible
   );
