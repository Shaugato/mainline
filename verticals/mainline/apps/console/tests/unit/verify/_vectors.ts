// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The cross-verifier golden set, loaded from `tests/vectors/`.
 *
 * These files are the CONTRACT with `packages/trappoint-verify` (Python, offline). The
 * shapes below are the only place the console describes them, and they are deliberately
 * narrow: a loader that shrugged at a missing member would let a truncated vector file
 * make the suite green.
 *
 * `import.meta.glob(..., '?raw')` is used rather than `node:fs` because the unit project's
 * `types` list is `["vite/client", "vitest/globals"]` — the application must not be able to
 * reach a Node global by accident, and that is not this worker's file to change.
 */

import type { LedgerPayload } from '../../../src/verify/ledger';

const RAW = import.meta.glob<string>('/tests/vectors/*.json', {
  query: '?raw',
  import: 'default',
  eager: true,
});

function load(name: string): unknown {
  const text = RAW[`/tests/vectors/${name}`];
  if (text === undefined) {
    throw new Error(
      `tests/vectors/${name} was not found. The vector set is the contract with ` +
        'packages/trappoint-verify; it is committed, not generated at test time.',
    );
  }
  return JSON.parse(text);
}

// ── Shapes ─────────────────────────────────────────────────────────────────

export interface JcsCase {
  readonly id: string;
  readonly note: string;
  readonly input_text: string;
  readonly canonical: string;
  readonly canonical_bytes: number;
  readonly sha256: string;
}

export interface JcsRefusal {
  readonly id: string;
  readonly note: string;
  readonly value_kind?: string;
  readonly input_text?: string;
  readonly error: string;
  readonly enforced_by: 'both' | 'python-only';
}

export interface JcsVectors {
  readonly cases: readonly JcsCase[];
  readonly refusals: readonly JcsRefusal[];
  readonly number_premise: string;
}

export interface Rfc6962Leaf {
  readonly seq: number;
  readonly canon_bytes_utf8: string;
  readonly canon_bytes_b64: string;
  readonly canon_bytes_length: number;
  readonly leaf_hash_hex: string;
  readonly link_hash_hex: string;
  readonly prev_link_hash_hex: string;
}

export interface Rfc6962Vectors {
  readonly empty_tree_root: string;
  readonly node_hash_cases: readonly {
    readonly id: string;
    readonly left: string;
    readonly right: string;
    readonly hash: string;
  }[];
  readonly leaves: readonly Rfc6962Leaf[];
  readonly roots: readonly { readonly tree_size: number; readonly root_hex: string }[];
  readonly inclusion_proofs: readonly {
    readonly id: string;
    readonly seq: number;
    readonly tree_size: number;
    readonly leaf_hash_hex: string;
    readonly root_hex: string;
    readonly path_hex: readonly string[];
    readonly expect: 'pass' | 'fail';
  }[];
  readonly consistency_proofs: readonly {
    readonly id: string;
    readonly from_size: number;
    readonly to_size: number;
    readonly from_root_hex: string;
    readonly to_root_hex: string;
    readonly path_hex: readonly string[];
    readonly expect: 'pass' | 'fail';
  }[];
  readonly negative: readonly {
    readonly id: string;
    readonly kind: 'inclusion' | 'consistency';
    readonly seq?: number;
    readonly tree_size?: number;
    readonly leaf_hash_hex?: string;
    readonly root_hex?: string;
    readonly from_size?: number;
    readonly to_size?: number;
    readonly from_root_hex?: string;
    readonly to_root_hex?: string;
    readonly path_hex: readonly string[];
    readonly expect: 'fail';
  }[];
}

export interface CheckpointKey {
  readonly id: string;
  readonly origin: string;
  readonly key_id_hex: string;
  readonly spki_der_hex: string;
  readonly spki_der_b64: string;
  readonly vkey: string;
}

export interface CheckpointCase {
  readonly id: string;
  readonly note: string;
  readonly trust: readonly string[];
  readonly note_text?: string;
  readonly full_note: string;
  readonly expect: 'verified' | 'failed' | 'malformed';
  readonly expect_reason_contains?: string;
  readonly expect_parsed?: {
    readonly origin: string;
    readonly tree_size: number;
    readonly root_hex: string;
    readonly extensions: Readonly<Record<string, string>>;
  };
  readonly expect_ignored_signature_names?: readonly string[];
  readonly signed_text_sha256?: string;
}

export interface CheckpointVectors {
  readonly keys: { readonly trusted: CheckpointKey; readonly adversary: CheckpointKey };
  readonly cases: readonly CheckpointCase[];
  readonly vkey_parsing: readonly {
    readonly id: string;
    readonly note: string;
    readonly vkey: string;
    readonly expect?: {
      readonly name: string;
      readonly key_id_hex: string;
      readonly algorithm: number;
      readonly spki_der_hex: string;
    };
    readonly expect_error?: string;
  }[];
}

export interface SilenceVectors {
  readonly reading: string;
  readonly candidate_leaves: readonly {
    readonly index: number;
    readonly canon_bytes_utf8: string;
    readonly leaf_hash_hex: string;
    readonly score: string;
  }[];
  readonly cases: readonly {
    readonly id: string;
    readonly note: string;
    readonly receipt: {
      readonly candidate_root: string;
      readonly theta: string;
      readonly s: number;
      readonly n: number;
      readonly boundary_proof: {
        readonly leaf_s: BoundaryLeafVector | null;
        readonly leaf_s_plus_1: BoundaryLeafVector | null;
      };
    };
    readonly expect: 'pass' | 'fail';
    readonly expect_reason_contains?: string;
  }[];
}

export interface BoundaryLeafVector {
  readonly index: number;
  readonly leaf_hash_hex: string;
  readonly score: string;
  readonly path_hex: readonly string[];
}

export interface LedgerPayloadVector {
  readonly note: string;
  readonly vkey: string;
  readonly canon_src_sha256: string;
  readonly envelope: {
    readonly envelope_version: 1;
    readonly resource: string;
    readonly schema_id: string;
    readonly staged: boolean;
    readonly staged_note: string;
    readonly data: LedgerPayload;
  };
  readonly expect: {
    readonly overall: 'pass' | 'bounded' | 'fail';
    readonly reason: string;
    readonly pass: readonly string[];
    readonly skip: readonly string[];
  };
}

export interface VectorIndex {
  readonly vectors_version: number;
  readonly frozen_at: string;
  readonly contract: string;
  readonly files: readonly { readonly path: string; readonly kind: string; readonly spec: string }[];
  readonly counts: Readonly<Record<string, number>>;
}

// ── Accessors ──────────────────────────────────────────────────────────────

export const vectorIndex = (): VectorIndex => load('index.json') as VectorIndex;
export const jcsVectors = (): JcsVectors => load('jcs.json') as JcsVectors;
export const rfc6962Vectors = (): Rfc6962Vectors => load('rfc6962.json') as Rfc6962Vectors;
export const checkpointVectors = (): CheckpointVectors =>
  load('checkpoint.json') as CheckpointVectors;
export const silenceVectors = (): SilenceVectors =>
  load('silence-boundary.json') as SilenceVectors;
export const ledgerPayloadVector = (): LedgerPayloadVector =>
  load('ledger-payload.json') as LedgerPayloadVector;

/** The vector envelope as raw text, for a caller that has to re-seal it into a bundle. */
export function ledgerPayloadText(): string {
  const text = RAW['/tests/vectors/ledger-payload.json'];
  if (text === undefined) throw new Error('tests/vectors/ledger-payload.json was not found.');
  return JSON.stringify((JSON.parse(text) as LedgerPayloadVector).envelope);
}

/** Every committed vector file, so a totality test can assert the index names them all. */
export function vectorFileNames(): readonly string[] {
  return Object.keys(RAW)
    .map((key) => key.replace('/tests/vectors/', ''))
    .sort();
}
