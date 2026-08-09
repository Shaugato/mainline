// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * RFC 6962 §2.1 — Merkle Tree Hash, inclusion proofs and consistency proofs.
 *
 * These are `trappoint-verify` checks 1, 2, 3 and 9, recomputed in the reader's browser
 * from the same bytes the offline verifier consumes. `tests/vectors/rfc6962.json` is the
 * cross-verifier golden set; every value in it is asserted equal to the frozen worked
 * example in `spec/wire/checkpoint.md` §7.2 at generation time.
 *
 * ── WHY BOTH A TREE AND A CHAIN ───────────────────────────────────────────────────
 *
 * The link chain — `link_hash[i] = SHA-256(link_hash[i−1] ‖ leaf_hash[i])` — is what
 * explains non-omission to a jury: *entry 4 names entry 3*. It is not what PROVES it. A
 * rogue DBA who deletes leaf *k*, renumbers and recomputes every `link_hash` produces a
 * chain that verifies perfectly. What that attack cannot survive is a **consistency
 * proof** against a root an independent party already holds. Both are implemented here,
 * and `docs/in-browser-verification.md` states which one carries the argument.
 *
 * ── DOMAIN SEPARATION IS THE WHOLE SECURITY ARGUMENT ──────────────────────────────
 *
 * `SHA-256(0x00 ‖ canon_bytes)` for a leaf and `SHA-256(0x01 ‖ left ‖ right)` for a node.
 * Without the prefix bytes, a leaf whose `canon_bytes` happened to equal the 64-byte
 * concatenation of two node hashes could be presented as that interior node — the
 * second-preimage attack RFC 6962 §2.1 exists to prevent. `tests/vectors/rfc6962.json`
 * carries a `node-domain-separation` case so that an implementation which drops the
 * prefix fails a vector rather than passing quietly.
 *
 * Everything below is async because the digest oracle is (WebCrypto is a promise API).
 * The recursion is over slices of a leaf-hash array, exactly as RFC 6962 defines it,
 * rather than over an index-arithmetic shortcut: the shortcut is faster and is where
 * every off-by-one in this family of bugs lives, and these trees are hundreds of leaves.
 */

import { concat, equalBytes, toHex } from './bytes';
import type { Sha256Oracle } from './sha256';

export const LEAF_PREFIX = new Uint8Array([0x00]);
export const NODE_PREFIX = new Uint8Array([0x01]);

/** 32 zero bytes: the genesis value the first link hash is computed against. */
export const GENESIS_LINK = new Uint8Array(32);

/** `leaf_hash = SHA-256(0x00 ‖ canon_bytes)` (RFC 6962 §2.1). */
export async function leafHash(oracle: Sha256Oracle, canonBytes: Uint8Array): Promise<Uint8Array> {
  return oracle.digest(concat(LEAF_PREFIX, canonBytes));
}

/** `node_hash = SHA-256(0x01 ‖ left ‖ right)` (RFC 6962 §2.1). */
export async function nodeHash(
  oracle: Sha256Oracle,
  left: Uint8Array,
  right: Uint8Array,
): Promise<Uint8Array> {
  return oracle.digest(concat(NODE_PREFIX, left, right));
}

/** The largest power of two STRICTLY less than `n`. RFC 6962's `k`. */
export function largestPowerOfTwoBelow(n: number): number {
  if (n < 2) throw new RangeError(`k is defined for n >= 2; got ${n}`);
  let k = 1;
  while (k * 2 < n) k *= 2;
  return k;
}

/**
 * `MTH(D[n])` — the Merkle Tree Hash of a list of leaf hashes.
 *
 * `MTH({}) = SHA-256("")`, which is what a size-0 checkpoint commits to. A verifier that
 * refuses the empty tree is a verifier that cannot let a log prove it was empty when it
 * was empty.
 */
export async function merkleTreeHash(
  oracle: Sha256Oracle,
  leaves: readonly Uint8Array[],
): Promise<Uint8Array> {
  if (leaves.length === 0) return oracle.digest(new Uint8Array(0));
  if (leaves.length === 1) {
    const only = leaves[0];
    if (only === undefined) throw new RangeError('leaf 0 is missing');
    return only;
  }
  const k = largestPowerOfTwoBelow(leaves.length);
  const left = await merkleTreeHash(oracle, leaves.slice(0, k));
  const right = await merkleTreeHash(oracle, leaves.slice(k));
  return nodeHash(oracle, left, right);
}

/** The audit path for leaf `m` in a tree of `leaves` (RFC 6962 §2.1.1). */
export async function inclusionPath(
  oracle: Sha256Oracle,
  m: number,
  leaves: readonly Uint8Array[],
): Promise<Uint8Array[]> {
  if (m < 0 || m >= leaves.length) throw new RangeError(`leaf index ${m} is outside [0, ${leaves.length})`);
  if (leaves.length === 1) return [];
  const k = largestPowerOfTwoBelow(leaves.length);
  if (m < k) {
    const rest = await merkleTreeHash(oracle, leaves.slice(k));
    return [...(await inclusionPath(oracle, m, leaves.slice(0, k))), rest];
  }
  const rest = await merkleTreeHash(oracle, leaves.slice(0, k));
  return [...(await inclusionPath(oracle, m - k, leaves.slice(k))), rest];
}

/** The consistency proof between sizes `m` and `leaves.length` (RFC 6962 §2.1.2). */
export async function consistencyPath(
  oracle: Sha256Oracle,
  m: number,
  leaves: readonly Uint8Array[],
): Promise<Uint8Array[]> {
  if (m < 1 || m > leaves.length) throw new RangeError(`from_size ${m} is outside [1, ${leaves.length}]`);
  return subproof(oracle, m, leaves, true);
}

async function subproof(
  oracle: Sha256Oracle,
  m: number,
  leaves: readonly Uint8Array[],
  b: boolean,
): Promise<Uint8Array[]> {
  if (m === leaves.length) return b ? [] : [await merkleTreeHash(oracle, leaves)];
  const k = largestPowerOfTwoBelow(leaves.length);
  if (m <= k) {
    const right = await merkleTreeHash(oracle, leaves.slice(k));
    return [...(await subproof(oracle, m, leaves.slice(0, k), b)), right];
  }
  const left = await merkleTreeHash(oracle, leaves.slice(0, k));
  return [...(await subproof(oracle, m - k, leaves.slice(k), false)), left];
}

// ── Verification ───────────────────────────────────────────────────────────

export interface ProofOutcome {
  readonly ok: boolean;
  /** The root the path actually reconstructs, as lowercase hex. Shown on screen. */
  readonly computedRootHex: string;
  /** Verbatim. Empty when `ok`. */
  readonly reason: string;
  /** Every intermediate hash, so the surface can SHOW the recomputation. */
  readonly steps: readonly ProofStep[];
}

export interface ProofStep {
  readonly index: number;
  readonly side: 'left' | 'right';
  readonly sibling: string;
  readonly result: string;
}

/**
 * Verify that `leafHashBytes` at index `seq` of a tree of `treeSize` leaves is committed
 * by `expectedRoot`, using `path`.
 *
 * The algorithm is RFC 6962 §2.1.1's verification form, written with the same `sn`/`fn`
 * variables the RFC uses so a reader can follow along. It refuses a path that is the
 * wrong LENGTH rather than stopping early: a short path that happens to reconstruct the
 * root is exactly the proof a forger would supply.
 */
export async function verifyInclusion(
  oracle: Sha256Oracle,
  options: {
    readonly seq: number;
    readonly treeSize: number;
    readonly leafHash: Uint8Array;
    readonly path: readonly Uint8Array[];
    readonly expectedRoot: Uint8Array;
  },
): Promise<ProofOutcome> {
  const { seq, treeSize, path, expectedRoot } = options;
  const steps: ProofStep[] = [];

  if (treeSize <= 0) {
    return fail('tree_size must be at least 1 for an inclusion proof', steps);
  }
  if (seq < 0 || seq >= treeSize) {
    return fail(`seq ${seq} is outside [0, ${treeSize})`, steps);
  }

  let fn = seq;
  let sn = treeSize - 1;
  let result = options.leafHash;
  let consumed = 0;

  while (sn !== 0) {
    const sibling = path[consumed];
    if (sibling === undefined) {
      return fail(
        `the path ran out after ${consumed} sibling(s) but the tree still has levels to climb. ` +
          'A path shorter than the tree depth cannot be completed, and a verifier that stopped ' +
          'here would accept a truncated proof.',
        steps,
      );
    }
    consumed += 1;

    if (fn % 2 === 1 || fn === sn) {
      result = await nodeHash(oracle, sibling, result);
      steps.push({ index: consumed - 1, side: 'left', sibling: toHex(sibling), result: toHex(result) });
      while (fn % 2 === 0 && fn !== 0) {
        fn = Math.floor(fn / 2);
        sn = Math.floor(sn / 2);
      }
    } else {
      result = await nodeHash(oracle, result, sibling);
      steps.push({ index: consumed - 1, side: 'right', sibling: toHex(sibling), result: toHex(result) });
    }
    fn = Math.floor(fn / 2);
    sn = Math.floor(sn / 2);
  }

  if (consumed !== path.length) {
    return fail(
      `the path carries ${path.length} siblings but the tree needed ${consumed}. A proof with ` +
        'spare elements has not been checked against the shape of the tree it claims to be from.',
      steps,
    );
  }
  if (!equalBytes(result, expectedRoot)) {
    return fail(
      `the path reconstructs ${toHex(result)}, which is not the root ${toHex(expectedRoot)}.`,
      steps,
      toHex(result),
    );
  }
  return { ok: true, computedRootHex: toHex(result), reason: '', steps };
}

/**
 * Verify a consistency proof: the tree at size `from` is a prefix of the tree at size
 * `to` (RFC 6962 §2.1.2).
 *
 * This is the check that catches *delete leaf k, renumber, recompute every link_hash* —
 * the attack the link chain cannot see, because the chain recomputes perfectly after it.
 */
export async function verifyConsistency(
  oracle: Sha256Oracle,
  options: {
    readonly from: number;
    readonly to: number;
    readonly fromRoot: Uint8Array;
    readonly toRoot: Uint8Array;
    readonly path: readonly Uint8Array[];
  },
): Promise<ProofOutcome> {
  const { from, to, fromRoot, toRoot, path } = options;
  const steps: ProofStep[] = [];

  if (from < 1) return fail(`from_size ${from} must be at least 1`, steps);
  if (to < from) return fail(`to_size ${to} is smaller than from_size ${from}`, steps);
  if (from === to) {
    if (path.length !== 0) {
      return fail('a consistency proof for m == n must be empty', steps);
    }
    if (!equalBytes(fromRoot, toRoot)) {
      return fail('m == n but the two roots differ', steps);
    }
    return { ok: true, computedRootHex: toHex(toRoot), reason: '', steps };
  }

  const proof = [...path];

  // RFC 6962 §2.1.2: when m is an exact power of two the first node is implicit and is
  // the old root itself. Prepending it is what makes the loop below uniform; omitting the
  // special case is the classic consistency-proof bug.
  let fn = from - 1;
  let sn = to - 1;
  if ((from & (from - 1)) === 0) {
    proof.unshift(fromRoot);
  }
  while (fn % 2 === 1) {
    fn = Math.floor(fn / 2);
    sn = Math.floor(sn / 2);
  }

  const first = proof[0];
  if (first === undefined) return fail('the consistency proof is empty', steps);
  let fr = first;
  let sr = first;
  let consumed = 1;

  while (sn !== 0) {
    if (fn % 2 === 1 || fn === sn) {
      const sibling = proof[consumed];
      if (sibling === undefined) {
        return fail(
          `the proof ran out after ${consumed} element(s); ${to} leaves need more.`,
          steps,
        );
      }
      consumed += 1;
      if (fn % 2 === 1) fr = await nodeHash(oracle, sibling, fr);
      sr = await nodeHash(oracle, sibling, sr);
      steps.push({
        index: consumed - 1,
        side: 'left',
        sibling: toHex(sibling),
        result: toHex(sr),
      });
      while (fn % 2 === 0 && fn !== 0) {
        fn = Math.floor(fn / 2);
        sn = Math.floor(sn / 2);
      }
    } else {
      const sibling = proof[consumed];
      if (sibling === undefined) {
        return fail(
          `the proof ran out after ${consumed} element(s); ${to} leaves need more.`,
          steps,
        );
      }
      consumed += 1;
      sr = await nodeHash(oracle, sr, sibling);
      steps.push({
        index: consumed - 1,
        side: 'right',
        sibling: toHex(sibling),
        result: toHex(sr),
      });
    }
    fn = Math.floor(fn / 2);
    sn = Math.floor(sn / 2);
  }

  if (consumed !== proof.length) {
    return fail(
      `the proof carries ${proof.length} elements but ${consumed} were needed.`,
      steps,
    );
  }
  if (!equalBytes(fr, fromRoot)) {
    return fail(
      `the proof reconstructs ${toHex(fr)} for size ${from}, which is not the recorded root ` +
        `${toHex(fromRoot)}. The earlier tree was not a prefix of the later one.`,
      steps,
      toHex(sr),
    );
  }
  if (!equalBytes(sr, toRoot)) {
    return fail(
      `the proof reconstructs ${toHex(sr)} for size ${to}, which is not the recorded root ` +
        `${toHex(toRoot)}.`,
      steps,
      toHex(sr),
    );
  }
  return { ok: true, computedRootHex: toHex(sr), reason: '', steps };
}

function fail(reason: string, steps: readonly ProofStep[], computed = ''): ProofOutcome {
  return { ok: false, computedRootHex: computed, reason, steps };
}

// ── The link chain (check 9) ───────────────────────────────────────────────

export interface LinkChainOutcome {
  readonly ok: boolean;
  readonly reason: string;
  /** Recomputed link hashes, in order, as lowercase hex. */
  readonly computed: readonly string[];
}

/**
 * Recompute the link chain and assert `seq` is dense from 0.
 *
 * A gap MEANS tampering. There is no sequence generator in this deployment that could
 * have produced one — `CREATE SEQUENCE`, `nextval`, `SERIAL` and `unique_rowid()` are
 * refused by a CI lint, and that lint is load-bearing rather than decorative because the
 * cluster would otherwise accept them. The ledger is gap-free by compare-and-set on
 * `UNIQUE (subject, prev_seq)`.
 */
export async function verifyLinkChain(
  oracle: Sha256Oracle,
  leaves: readonly {
    readonly seq: number;
    readonly leafHash: Uint8Array;
    readonly linkHash: Uint8Array;
    readonly prevLinkHash: Uint8Array;
  }[],
): Promise<LinkChainOutcome> {
  const computed: string[] = [];
  // Annotated: `new Uint8Array(32)` narrows to `Uint8Array<ArrayBuffer>`, while a digest
  // returns the `ArrayBufferLike` form, and the chain assigns one to the other.
  let previous: Uint8Array = GENESIS_LINK;

  for (let i = 0; i < leaves.length; i += 1) {
    const leaf = leaves[i];
    if (leaf === undefined) return { ok: false, reason: `leaf ${i} is missing`, computed };
    if (leaf.seq !== i) {
      return {
        ok: false,
        reason:
          `seq is not dense: position ${i} carries seq ${leaf.seq}. A gap in this ledger is not ` +
          'a missing row — there is no sequence generator in this deployment that could have ' +
          'produced one, so a gap means tampering.',
        computed,
      };
    }
    if (!equalBytes(leaf.prevLinkHash, previous)) {
      return {
        ok: false,
        reason:
          `leaf ${i} names prev_link_hash ${toHex(leaf.prevLinkHash)} but the chain is at ` +
          `${toHex(previous)}.`,
        computed,
      };
    }
    const link = await oracle.digest(concat(previous, leaf.leafHash));
    computed.push(toHex(link));
    if (!equalBytes(link, leaf.linkHash)) {
      return {
        ok: false,
        reason:
          `leaf ${i}: SHA-256(prev_link ‖ leaf_hash) is ${toHex(link)}, but the row carries ` +
          `${toHex(leaf.linkHash)}.`,
        computed,
      };
    }
    previous = link;
  }

  return { ok: true, reason: '', computed };
}
