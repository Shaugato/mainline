// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The vector set is TOTAL: the index names every file, and every file is named.
 *
 * This is the check that stops the contract from rotting quietly. A vector file added to
 * the directory but not to `index.json` is a case `packages/trappoint-verify` will never
 * be told to run — the two implementations would then agree on everything either of them
 * happened to check, which is not the same as agreeing.
 *
 * A file named in the index but absent from the directory fails in the loader, loudly, at
 * the first test that reads it. The direction this file adds is the other one.
 */

import { describe, expect, it } from 'vitest';

import {
  checkpointVectors,
  jcsVectors,
  ledgerPayloadVector,
  rfc6962Vectors,
  silenceVectors,
  vectorFileNames,
  vectorIndex,
} from './_vectors';

const index = vectorIndex();

describe('the index and the directory agree', () => {
  it('names every committed vector file exactly once', () => {
    const onDisk = vectorFileNames().filter((name) => name !== 'index.json');
    const named = index.files.map((entry) => entry.path).sort();
    expect(named).toEqual(onDisk);
    expect(new Set(named).size).toBe(named.length);
  });

  it('gives every file a subject and a specification', () => {
    for (const entry of index.files) {
      expect(entry.kind.length, entry.path).toBeGreaterThan(0);
      expect(entry.spec.length, entry.path).toBeGreaterThan(0);
    }
  });

  it('states the contract, in the words the doc quotes', () => {
    expect(index.contract).toContain('byte for byte');
    expect(index.contract).toContain('never edited to make an implementation pass');
    expect(index.frozen_at).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});

describe('the counts in the index are the counts in the files', () => {
  it('matches every declared count', () => {
    const jcs = jcsVectors();
    const rfc = rfc6962Vectors();
    const checkpoint = checkpointVectors();
    const silence = silenceVectors();
    const ledger = ledgerPayloadVector();

    expect(index.counts.jcs_cases).toBe(jcs.cases.length);
    expect(index.counts.jcs_refusals).toBe(jcs.refusals.length);
    expect(index.counts.rfc6962_inclusion).toBe(rfc.inclusion_proofs.length);
    expect(index.counts.rfc6962_consistency).toBe(rfc.consistency_proofs.length);
    expect(index.counts.rfc6962_negative).toBe(rfc.negative.length);
    expect(index.counts.checkpoint_cases).toBe(checkpoint.cases.length);
    expect(index.counts.checkpoint_vkey).toBe(checkpoint.vkey_parsing.length);
    expect(index.counts.silence_cases).toBe(silence.cases.length);
    expect(index.counts.ledger_leaves).toBe(ledger.envelope.data.leaves.length);
    expect(index.counts.ledger_checkpoints).toBe(ledger.envelope.data.checkpoints.length);
  });

  it('carries both accepting AND refusing cases in every family', () => {
    // A vector family with no negative case asserts that a function returns true.
    expect(jcsVectors().refusals.length).toBeGreaterThan(0);
    expect(rfc6962Vectors().negative.length).toBeGreaterThan(0);
    expect(
      checkpointVectors().cases.filter((entry) => entry.expect !== 'verified').length,
    ).toBeGreaterThan(0);
    expect(silenceVectors().cases.filter((entry) => entry.expect === 'fail').length).toBeGreaterThan(
      0,
    );
  });
});
