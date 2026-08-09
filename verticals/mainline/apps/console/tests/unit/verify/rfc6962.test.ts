// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * RFC 6962, against the frozen worked example in `spec/wire/checkpoint.md` §7.2.
 *
 * The vector generator asserted every leaf hash, link hash and root below equal to the
 * published value before writing the file, so this suite is checking the browser against
 * the SPECIFICATION rather than against itself.
 *
 * The negative cases carry the weight. A proof verifier that only ever sees valid proofs
 * is a function that returns true.
 */

import { describe, expect, it } from 'vitest';

import { digestFromHex, fromBase64, toHex, utf8 } from '../../../src/verify/bytes';
import {
  GENESIS_LINK,
  consistencyPath,
  inclusionPath,
  largestPowerOfTwoBelow,
  leafHash,
  merkleTreeHash,
  nodeHash,
  verifyConsistency,
  verifyInclusion,
  verifyLinkChain,
} from '../../../src/verify/rfc6962';
import { SOFTWARE_ORACLE } from '../../../src/verify/sha256';

import { rfc6962Vectors } from './_vectors';

const oracle = SOFTWARE_ORACLE;
const vectors = rfc6962Vectors();

async function leafHashes(): Promise<Uint8Array[]> {
  const hashes: Uint8Array[] = [];
  for (const leaf of vectors.leaves) {
    hashes.push(await leafHash(oracle, fromBase64(leaf.canon_bytes_b64)));
  }
  return hashes;
}

describe('leaf and node hashing', () => {
  it('reproduces every published leaf hash from the canon bytes', async () => {
    for (const leaf of vectors.leaves) {
      const bytes = utf8(leaf.canon_bytes_utf8);
      expect(bytes.byteLength).toBe(leaf.canon_bytes_length);
      expect(toHex(await leafHash(oracle, bytes))).toBe(leaf.leaf_hash_hex);
    }
  });

  it('carries the base64 and the text form of the same bytes', () => {
    for (const leaf of vectors.leaves) {
      expect(toHex(fromBase64(leaf.canon_bytes_b64))).toBe(toHex(utf8(leaf.canon_bytes_utf8)));
    }
  });

  it.each(vectors.node_hash_cases.map((c) => [c.id, c] as const))('node hash %s', async (_id, c) => {
    expect(toHex(await nodeHash(oracle, digestFromHex(c.left), digestFromHex(c.right)))).toBe(c.hash);
  });

  it('separates the leaf and node domains', async () => {
    // SHA-256(0x01 ‖ l ‖ r) must not equal SHA-256(0x00 ‖ l ‖ r), or a leaf whose canon
    // bytes are a 64-byte concatenation could be presented as an interior node.
    const left = digestFromHex('00'.repeat(32));
    const right = digestFromHex('ff'.repeat(32));
    const asNode = await nodeHash(oracle, left, right);
    const asLeaf = await leafHash(oracle, new Uint8Array([...left, ...right]));
    expect(toHex(asNode)).not.toBe(toHex(asLeaf));
  });
});

describe('the Merkle Tree Hash', () => {
  it('is SHA-256("") for the empty tree', async () => {
    expect(toHex(await merkleTreeHash(oracle, []))).toBe(vectors.empty_tree_root);
  });

  it('reproduces the published root at every size', async () => {
    const hashes = await leafHashes();
    for (const { tree_size: size, root_hex: root } of vectors.roots) {
      expect(toHex(await merkleTreeHash(oracle, hashes.slice(0, size))), `size ${size}`).toBe(root);
    }
  });

  it('computes k as the largest power of two STRICTLY below n', () => {
    expect(largestPowerOfTwoBelow(2)).toBe(1);
    expect(largestPowerOfTwoBelow(3)).toBe(2);
    expect(largestPowerOfTwoBelow(4)).toBe(2);
    expect(largestPowerOfTwoBelow(5)).toBe(4);
    expect(largestPowerOfTwoBelow(8)).toBe(4);
    expect(() => largestPowerOfTwoBelow(1)).toThrow();
  });
});

describe('inclusion proofs', () => {
  it.each(vectors.inclusion_proofs.map((p) => [p.id, p] as const))('%s verifies', async (_id, p) => {
    const outcome = await verifyInclusion(oracle, {
      seq: p.seq,
      treeSize: p.tree_size,
      leafHash: digestFromHex(p.leaf_hash_hex),
      path: p.path_hex.map((value) => digestFromHex(value)),
      expectedRoot: digestFromHex(p.root_hex),
    });
    expect(outcome.reason).toBe('');
    expect(outcome.ok).toBe(true);
    expect(outcome.computedRootHex).toBe(p.root_hex);
    expect(outcome.steps).toHaveLength(p.path_hex.length);
  });

  it('generates the same paths it verifies', async () => {
    const hashes = await leafHashes();
    for (const p of vectors.inclusion_proofs) {
      const generated = (await inclusionPath(oracle, p.seq, hashes)).map(toHex);
      expect(generated, p.id).toEqual([...p.path_hex]);
    }
  });
});

describe('consistency proofs', () => {
  it.each(vectors.consistency_proofs.map((p) => [p.id, p] as const))('%s verifies', async (_id, p) => {
    const outcome = await verifyConsistency(oracle, {
      from: p.from_size,
      to: p.to_size,
      fromRoot: digestFromHex(p.from_root_hex),
      toRoot: digestFromHex(p.to_root_hex),
      path: p.path_hex.map((value) => digestFromHex(value)),
    });
    expect(outcome.reason).toBe('');
    expect(outcome.ok).toBe(true);
    expect(outcome.computedRootHex).toBe(p.to_root_hex);
  });

  it('generates the same paths it verifies', async () => {
    const hashes = await leafHashes();
    for (const p of vectors.consistency_proofs) {
      const generated = (await consistencyPath(oracle, p.from_size, hashes.slice(0, p.to_size))).map(
        toHex,
      );
      expect(generated, p.id).toEqual([...p.path_hex]);
    }
  });

  it('accepts an empty proof only when m equals n', async () => {
    const hashes = await leafHashes();
    const root = await merkleTreeHash(oracle, hashes);
    const same = await verifyConsistency(oracle, {
      from: 5,
      to: 5,
      fromRoot: root,
      toRoot: root,
      path: [],
    });
    expect(same.ok).toBe(true);

    const different = await verifyConsistency(oracle, {
      from: 5,
      to: 5,
      fromRoot: root,
      toRoot: digestFromHex('ab'.repeat(32)),
      path: [],
    });
    expect(different.ok).toBe(false);
    expect(different.reason).toContain('roots differ');
  });
});

describe('the negative vectors — where the security actually lives', () => {
  it.each(vectors.negative.map((n) => [n.id, n] as const))('%s is refused', async (_id, n) => {
    if (n.kind === 'inclusion') {
      const outcome = await verifyInclusion(oracle, {
        seq: n.seq ?? 0,
        treeSize: n.tree_size ?? 0,
        leafHash: digestFromHex(n.leaf_hash_hex ?? ''),
        path: n.path_hex.map((value) => digestFromHex(value)),
        expectedRoot: digestFromHex(n.root_hex ?? ''),
      });
      expect(outcome.ok).toBe(false);
      expect(outcome.reason).not.toBe('');
      return;
    }
    const outcome = await verifyConsistency(oracle, {
      from: n.from_size ?? 0,
      to: n.to_size ?? 0,
      fromRoot: digestFromHex(n.from_root_hex ?? ''),
      toRoot: digestFromHex(n.to_root_hex ?? ''),
      path: n.path_hex.map((value) => digestFromHex(value)),
    });
    expect(outcome.ok).toBe(false);
    expect(outcome.reason).not.toBe('');
  });

  it('refuses a leaf hash with one bit flipped', async () => {
    const proof = vectors.inclusion_proofs[3];
    if (proof === undefined) throw new Error('vector set is truncated');
    const leaf = digestFromHex(proof.leaf_hash_hex);
    leaf[0] = (leaf[0] ?? 0) ^ 0x01;
    const outcome = await verifyInclusion(oracle, {
      seq: proof.seq,
      treeSize: proof.tree_size,
      leafHash: leaf,
      path: proof.path_hex.map((value) => digestFromHex(value)),
      expectedRoot: digestFromHex(proof.root_hex),
    });
    expect(outcome.ok).toBe(false);
    expect(outcome.reason).toContain('is not the root');
  });

  it('refuses a path with a spare element', async () => {
    const proof = vectors.inclusion_proofs[0];
    if (proof === undefined) throw new Error('vector set is truncated');
    const outcome = await verifyInclusion(oracle, {
      seq: proof.seq,
      treeSize: proof.tree_size,
      leafHash: digestFromHex(proof.leaf_hash_hex),
      path: [...proof.path_hex, 'cd'.repeat(32)].map((value) => digestFromHex(value)),
      expectedRoot: digestFromHex(proof.root_hex),
    });
    expect(outcome.ok).toBe(false);
    expect(outcome.reason).toContain('spare elements');
  });
});

describe('the link chain (check 9)', () => {
  it('recomputes the published chain and accepts dense seq', async () => {
    const hashes = await leafHashes();
    const rows = vectors.leaves.map((leaf, index) => ({
      seq: leaf.seq,
      leafHash: hashes[index] ?? new Uint8Array(32),
      linkHash: digestFromHex(leaf.link_hash_hex),
      prevLinkHash: digestFromHex(leaf.prev_link_hash_hex),
    }));
    const outcome = await verifyLinkChain(oracle, rows);
    expect(outcome.reason).toBe('');
    expect(outcome.ok).toBe(true);
    expect(outcome.computed).toEqual(vectors.leaves.map((leaf) => leaf.link_hash_hex));
    expect(toHex(GENESIS_LINK)).toBe(vectors.leaves[0]?.prev_link_hash_hex);
  });

  it('refuses a gap in seq, and names it as tampering rather than absence', async () => {
    const hashes = await leafHashes();
    const rows = vectors.leaves
      .filter((leaf) => leaf.seq !== 2)
      .map((leaf) => ({
        seq: leaf.seq,
        leafHash: hashes[leaf.seq] ?? new Uint8Array(32),
        linkHash: digestFromHex(leaf.link_hash_hex),
        prevLinkHash: digestFromHex(leaf.prev_link_hash_hex),
      }));
    const outcome = await verifyLinkChain(oracle, rows);
    expect(outcome.ok).toBe(false);
    expect(outcome.reason).toContain('a gap means tampering');
  });

  it('refuses a chain whose prev_link_hash does not follow', async () => {
    const hashes = await leafHashes();
    const rows = vectors.leaves.map((leaf, index) => ({
      seq: leaf.seq,
      leafHash: hashes[index] ?? new Uint8Array(32),
      linkHash: digestFromHex(leaf.link_hash_hex),
      prevLinkHash:
        index === 3 ? digestFromHex('11'.repeat(32)) : digestFromHex(leaf.prev_link_hash_hex),
    }));
    const outcome = await verifyLinkChain(oracle, rows);
    expect(outcome.ok).toBe(false);
    expect(outcome.reason).toContain('but the chain is at');
  });
});
