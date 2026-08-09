// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The check suite over a whole `ledger` payload.
 *
 * Two payloads, deliberately:
 *
 *   • `tests/vectors/ledger-payload.json` — cryptographically real. Every hash, chain
 *     link, proof and signature is genuine, so the suite has a GREEN path that is not a
 *     mock. It is the payload the browser spec tampers with.
 *   • `fixtures/bundles/blk-07/` — hand-authored, and its own `ledger/bundle.json` says
 *     *running trappoint-verify against it MUST fail, and that failure is the correct
 *     outcome*. This suite makes no exception for it. A verifier with a fixture allowlist
 *     is not a verifier.
 */

import { describe, expect, it } from 'vitest';

import { createContractRegistry } from '../../../src/data/contracts';
import { formatErrors } from '../../../src/data/schema';
import { toBase64, utf8 } from '../../../src/verify/bytes';
import { operatorConfig, NO_ANCHOR } from '../../../src/verify/config';
import {
  SPLIT_VIEW_LIMIT,
  recomputeRoot,
  verifyLedger,
  type CheckReport,
  type LedgerPayload,
} from '../../../src/verify/ledger';
import { SOFTWARE_ORACLE } from '../../../src/verify/sha256';

import { ledgerPayloadVector } from './_vectors';

const oracle = SOFTWARE_ORACLE;
const vector = ledgerPayloadVector();
const config = operatorConfig(vector.vkey, vector.canon_src_sha256);
const subtle = globalThis.crypto?.subtle;
const AT = '2026-08-09T00:00:00.000Z';

function statusOf(report: CheckReport, name: string): string {
  const check = report.checks.find((entry) => entry.name === name);
  if (check === undefined) throw new Error(`no check named ${name} in the report`);
  return check.status;
}

/**
 * A deep, MUTABLE copy of the vector payload.
 *
 * `LedgerPayload` is `readonly` all the way down, which is right for the module under
 * test and wrong for a tamper test whose whole job is to change one field. The mutable
 * mirror below is declared rather than cast through `unknown`, so a field renamed in
 * `src/verify/ledger.ts` breaks this file at compile time instead of at assertion time.
 */
interface MutableLedger {
  site_code: string;
  checkpoints: Record<string, unknown>[];
  leaves: Record<string, unknown>[];
  nodes?: Record<string, unknown>[];
  inclusion_proofs: Record<string, unknown>[];
  consistency_proofs?: Record<string, unknown>[];
  cosignatures?: Record<string, unknown>[];
  unwitnessed_debt?: Record<string, unknown>[];
}

function clone(): MutableLedger {
  return JSON.parse(JSON.stringify(vector.envelope.data)) as MutableLedger;
}

/** The mutated copy, back in the shape `verifyLedger` accepts. */
function asPayload(mutated: MutableLedger): LedgerPayload {
  return mutated as unknown as LedgerPayload;
}

describe('the vector envelope is a real payload, not a shape', () => {
  it('validates against contracts/ledger.schema.json', () => {
    const registry = createContractRegistry();
    const result = registry.validate(vector.envelope.schema_id, vector.envelope);
    expect(result.valid, formatErrors(result.errors)).toBe(true);
  });

  it('declares itself staged, and says exactly what is staged', () => {
    expect(vector.envelope.staged).toBe(true);
    expect(vector.envelope.staged_note).toContain('Cryptographically real, operationally staged');
    expect(vector.envelope.staged_note).toContain('never as a measurement of a live ledger');
  });

  it('recomputes to the root the head checkpoint signed', async () => {
    const { rootHex, leafCount } = await recomputeRoot(oracle, vector.envelope.data);
    const head = vector.envelope.data.checkpoints.at(-1);
    expect(leafCount).toBe(head?.tree_size);
    expect(rootHex).toBe(head?.root_hex);
  });
});

describe('the green path', () => {
  it.runIf(subtle !== undefined)('passes every check the vector says it passes', async () => {
    const report = await verifyLedger(vector.envelope.data, {
      oracle,
      config,
      subtle,
      now: () => new Date(AT),
    });
    for (const name of vector.expect.pass) {
      const check = report.checks.find((entry) => entry.name === name);
      expect(check?.status, `${name}: ${check?.detail ?? 'missing'}`).toBe('pass');
    }
    for (const name of vector.expect.skip) {
      expect(statusOf(report, name), name).toBe('skip');
    }
    expect(report.at).toBe(AT);
    expect(report.oracleName).toBe(oracle.name);
  });

  it.runIf(subtle !== undefined)('is BOUNDED, never clean, because six checks are not run', async () => {
    const report = await verifyLedger(vector.envelope.data, { oracle, config, subtle });
    expect(report.overall).toBe(vector.expect.overall);
    expect(report.overall).toBe('bounded');
    expect(report.summary).toContain('NOT RUN');
  });

  it.runIf(subtle !== undefined)('states the split-view limit on the quorum check', async () => {
    const report = await verifyLedger(vector.envelope.data, { oracle, config, subtle });
    const quorum = report.checks.find((entry) => entry.name === 'witness_quorum');
    expect(quorum?.status).toBe('pass');
    expect(quorum?.bounded).toContain(SPLIT_VIEW_LIMIT);
  });

  it.runIf(subtle !== undefined)('names every deferred check rather than omitting it', async () => {
    const report = await verifyLedger(vector.envelope.data, { oracle, config, subtle });
    const ids = report.checks.map((entry) => entry.id).sort((a, b) => a - b);
    // Registry ids 1..14 minus 15 and 16 (bundle-level, not payload-level), plus 0 for
    // the payload-versus-canon_bytes discrepancy report.
    expect(ids).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]);
    for (const check of report.checks) {
      expect(check.detail.length, check.name).toBeGreaterThan(20);
    }
  });
});

describe('one byte, and the report goes red', () => {
  it.runIf(subtle !== undefined)('a flipped canon byte fails the leaf hash check', async () => {
    const payload = clone();
    const leaf = payload.leaves[3];
    if (leaf === undefined) throw new Error('vector is truncated');
    const original = new TextDecoder().decode(utf8(atob(String(leaf.canon_bytes_b64))));
    const mutated = original.replace('"controlled"', '"uncontrolled"');
    expect(mutated).not.toBe(original);
    leaf.canon_bytes_b64 = toBase64(utf8(mutated));

    const report = await verifyLedger(asPayload(payload), { oracle, config, subtle });
    expect(report.overall).toBe('fail');
    expect(statusOf(report, 'leaf_hash_recomputation')).toBe('fail');
    const check = report.checks.find((entry) => entry.name === 'leaf_hash_recomputation');
    expect(check?.detail).toContain('leaf 3');
    expect(check?.recomputations.some((entry) => !entry.agrees)).toBe(true);
  });

  it.runIf(subtle !== undefined)('a re-signed note under a different key fails check 4', async () => {
    const payload = clone();
    const head = payload.checkpoints.at(-1);
    if (head === undefined) throw new Error('vector is truncated');
    // Same note text, a signature line the configured key did not produce: one base64
    // character of the signature is enough.
    const note = String(head.note);
    const broken = note.replace(/([A-Za-z0-9+/]{20})([A-Za-z0-9+/])/, (_m, a: string, b: string) =>
      `${a}${b === 'A' ? 'B' : 'A'}`,
    );
    expect(broken).not.toBe(note);
    head.note = broken;

    const report = await verifyLedger(asPayload(payload), { oracle, config, subtle });
    expect(statusOf(report, 'log_signature')).toBe('fail');
    expect(report.overall).toBe('fail');
  });

  it.runIf(subtle !== undefined)('a rewritten readable payload is reported as a discrepancy', async () => {
    const payload = clone();
    const leaf = payload.leaves[2];
    if (leaf === undefined) throw new Error('vector is truncated');
    leaf.payload = { ...(leaf.payload as Record<string, unknown>), severity: 1 };

    const report = await verifyLedger(asPayload(payload), { oracle, config, subtle });
    // The TREE is untouched: what was hashed still hashes correctly.
    expect(statusOf(report, 'leaf_hash_recomputation')).toBe('pass');
    expect(statusOf(report, 'payload_vs_canon_bytes')).toBe('fail');
    const check = report.checks.find((entry) => entry.name === 'payload_vs_canon_bytes');
    expect(check?.detail).toContain('what you can READ and what was SIGNED are not the same thing');
  });

  it.runIf(subtle !== undefined)('a deleted leaf fails density before it fails anything else', async () => {
    const payload = clone();
    payload.leaves = payload.leaves.filter((leaf) => leaf.seq !== 2);
    const report = await verifyLedger(asPayload(payload), { oracle, config, subtle });
    expect(statusOf(report, 'link_chain_and_density')).toBe('fail');
    expect(
      report.checks.find((entry) => entry.name === 'link_chain_and_density')?.detail,
    ).toContain('a gap means tampering');
  });

  it.runIf(subtle !== undefined)('a dropped consistency proof fails check 3', async () => {
    const payload = clone();
    payload.consistency_proofs = [];
    const report = await verifyLedger(asPayload(payload), { oracle, config, subtle });
    expect(statusOf(report, 'consistency_proof_every_pair')).toBe('fail');
  });

  it.runIf(subtle !== undefined)('a sandbox leaf fails check 13', async () => {
    const payload = clone();
    const first = payload.leaves[0];
    if (first === undefined) throw new Error('vector is truncated');
    first.is_sandbox = true;
    const report = await verifyLedger(asPayload(payload), { oracle, config, subtle });
    expect(statusOf(report, 'no_sandbox_leaf')).toBe('fail');
  });
});

describe('missing configuration SKIPS; it never passes and never accuses', () => {
  it('reports check 4 as skip with no trust anchor', async () => {
    const report = await verifyLedger(vector.envelope.data, { oracle, config: NO_ANCHOR, subtle });
    const check = report.checks.find((entry) => entry.name === 'log_signature');
    expect(check?.status).toBe('skip');
    expect(check?.detail).toContain('no verification key is configured');
    expect(report.overall).toBe('bounded');
  });

  it('reports check 10 as skip with no canonicaliser pin', async () => {
    const report = await verifyLedger(vector.envelope.data, { oracle, config: NO_ANCHOR, subtle });
    const check = report.checks.find((entry) => entry.name === 'canonicaliser_identity');
    expect(check?.status).toBe('skip');
    expect(check?.detail).toContain('marking its own homework');
  });

  it.runIf(subtle !== undefined)('fails check 10 when the pin disagrees with the signed note', async () => {
    const wrongPin = operatorConfig(vector.vkey, 'ab'.repeat(32));
    const report = await verifyLedger(vector.envelope.data, { oracle, config: wrongPin, subtle });
    const check = report.checks.find((entry) => entry.name === 'canonicaliser_identity');
    expect(check?.status).toBe('fail');
    expect(check?.detail).toContain('the pinned value is');
  });
});

describe('the staged demo fixture fails, and that is the correct outcome', () => {
  const FIXTURE = import.meta.glob<string>('/fixtures/sources/blk-07/payloads/ledger.json', {
    query: '?raw',
    import: 'default',
    eager: true,
  });

  it('carries hand-authored hash patterns that do not survive recomputation', async () => {
    const text = FIXTURE['/fixtures/sources/blk-07/payloads/ledger.json'];
    expect(text, 'the staged ledger fixture was not found').toBeDefined();
    const staged = (JSON.parse(text ?? '{}') as { data: LedgerPayload }).data;

    const report = await verifyLedger(staged, { oracle, config: NO_ANCHOR, subtle });
    expect(report.overall).toBe('fail');
    expect(statusOf(report, 'leaf_hash_recomputation')).toBe('fail');
    // The custody surface renders this verbatim. A demo that hid it would be the one
    // screen in this console that lied about provenance.
    expect(
      report.checks.find((entry) => entry.name === 'leaf_hash_recomputation')?.detail,
    ).toContain('do not hash to the value recorded against them');
  });
});
