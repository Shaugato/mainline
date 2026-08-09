// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Proof of Exhausted Recall — the boundary pair.
 *
 * The case that carries the suite is `per-hand-excluded-item`: a candidate scoring above θ
 * is dropped and the boundary moved up one. Every hash still verifies, the tree is intact,
 * and the receipt is internally consistent in every way except the one that matters — the
 * leaf now claimed to be the first EXCLUDED still scores above the threshold. That is what
 * "no item can be hand-excluded without breaking sortedness" means in code.
 */

import { describe, expect, it } from 'vitest';

import { fromBase64, toHex, utf8 } from '../../../src/verify/bytes';
import { leafHash } from '../../../src/verify/rfc6962';
import { SOFTWARE_ORACLE } from '../../../src/verify/sha256';
import {
  compareDecimal,
  verifyBoundary,
  type BoundaryLeaf,
  type SilenceBoundaryInput,
} from '../../../src/verify/silenceroot';

import { silenceVectors, type BoundaryLeafVector } from './_vectors';

const oracle = SOFTWARE_ORACLE;
const vectors = silenceVectors();

function toLeaf(vector: BoundaryLeafVector | null): BoundaryLeaf | null {
  if (vector === null) return null;
  return {
    index: vector.index,
    leafHashHex: vector.leaf_hash_hex,
    score: vector.score,
    pathHex: vector.path_hex,
  };
}

describe('the receipt states its indexing, and the vectors follow it', () => {
  it('reads s as a 1-based count of admitted leaves', () => {
    expect(vectors.reading).toContain('1-based');
    expect(vectors.reading).toContain('DESCENDING');
  });

  it('commits leaves that really are score-sorted descending', () => {
    const scores = vectors.candidate_leaves.map((leaf) => leaf.score);
    for (let i = 1; i < scores.length; i += 1) {
      expect(compareDecimal(scores[i - 1] ?? '0', scores[i] ?? '0')).toBeGreaterThanOrEqual(0);
    }
  });

  it('hashes each candidate leaf to the committed value', async () => {
    for (const leaf of vectors.candidate_leaves) {
      expect(toHex(await leafHash(oracle, utf8(leaf.canon_bytes_utf8)))).toBe(leaf.leaf_hash_hex);
    }
  });
});

describe('decimal comparison is exact, not floating point', () => {
  it('orders values IEEE-754 would confuse', () => {
    expect(compareDecimal('0.45', '0.45')).toBe(0);
    expect(compareDecimal('0.1', '0.10')).toBe(0);
    expect(compareDecimal('0.30000000000000004', '0.3')).toBe(1);
    expect(compareDecimal('-0.5', '0.1')).toBe(-1);
    expect(compareDecimal('10', '9.9')).toBe(1);
    expect(compareDecimal('0.9', '0.85')).toBe(1);
  });

  it('refuses anything that is not a plain decimal, including exponents', () => {
    expect(() => compareDecimal('1e-3', '0.1')).toThrow(/plain decimal/);
    expect(() => compareDecimal('', '0.1')).toThrow(/plain decimal/);
    expect(() => compareDecimal('.5', '0.1')).toThrow(/plain decimal/);
  });
});

describe('verifyBoundary', () => {
  it.each(vectors.cases.map((c) => [c.id, c] as const))('%s', async (_id, testCase) => {
    const receipt = testCase.receipt;
    const input: SilenceBoundaryInput = {
      candidateRootHex: receipt.candidate_root,
      theta: receipt.theta,
      s: receipt.s,
      n: receipt.n,
      leafS: toLeaf(receipt.boundary_proof.leaf_s),
      leafSPlusOne: toLeaf(receipt.boundary_proof.leaf_s_plus_1),
    };
    const outcome = await verifyBoundary(oracle, input);
    expect(
      outcome.status,
      `${testCase.note}\n${outcome.findings.map((f) => `${f.check}: ${f.detail}`).join('\n')}`,
    ).toBe(testCase.expect);

    if (testCase.expect === 'pass') {
      expect(outcome.findings).toHaveLength(0);
      expect(outcome.summary).toContain('not of the corpus');
    } else {
      expect(outcome.findings.length).toBeGreaterThan(0);
      if (testCase.expect_reason_contains !== undefined) {
        const joined = outcome.findings.map((f) => `${f.check} ${f.detail}`).join('\n');
        expect(joined.toLowerCase()).toContain(testCase.expect_reason_contains.toLowerCase());
      }
    }
  });

  it('reports s = 0 rather than passing it', async () => {
    const holds = vectors.cases.find((c) => c.id === 'per-boundary-holds');
    if (holds === undefined) throw new Error('vector set is truncated');
    const outcome = await verifyBoundary(oracle, {
      candidateRootHex: holds.receipt.candidate_root,
      theta: holds.receipt.theta,
      s: 0,
      n: holds.receipt.n,
      leafS: null,
      leafSPlusOne: null,
    });
    expect(outcome.status).toBe('fail');
    expect(outcome.findings[0]?.detail).toContain('establishes nothing about sortedness');
  });

  it('names the leaf whose inclusion path failed', async () => {
    const forged = vectors.cases.find((c) => c.id === 'per-forged-inclusion-path');
    if (forged === undefined) throw new Error('vector set is truncated');
    const outcome = await verifyBoundary(oracle, {
      candidateRootHex: forged.receipt.candidate_root,
      theta: forged.receipt.theta,
      s: forged.receipt.s,
      n: forged.receipt.n,
      leafS: toLeaf(forged.receipt.boundary_proof.leaf_s),
      leafSPlusOne: toLeaf(forged.receipt.boundary_proof.leaf_s_plus_1),
    });
    expect(outcome.inclusion.map((entry) => entry.which)).toEqual(['leaf_s', 'leaf_s_plus_1']);
    expect(outcome.inclusion[0]?.outcome.ok).toBe(true);
    expect(outcome.inclusion[1]?.outcome.ok).toBe(false);
  });

  it('refuses a candidate_root that is not a 32-byte digest', async () => {
    const outcome = await verifyBoundary(oracle, {
      candidateRootHex: 'deadbeef',
      theta: '0.45',
      s: 1,
      n: 2,
      leafS: null,
      leafSPlusOne: null,
    });
    expect(outcome.status).toBe('fail');
    expect(outcome.findings[0]?.check).toBe('candidate_root');
  });

  it('does not accept a base64 root smuggled in as hex', () => {
    // fromBase64 and fromHex are separate on purpose: one alphabet is a subset of the
    // other's characters, so a permissive decoder would silently accept the wrong form.
    expect(() => fromBase64('zz')).toThrow();
  });
});
