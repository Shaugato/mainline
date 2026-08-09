// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE RULE: a raw cosine never appears without its calibrated `p_relevant` beside it.
 *
 * `mainline_meas.recall_candidate.p_relevant` is a CALIBRATED value, and the DDL comment
 * says why in six words: *raw cosine never reaches a human*. A cosine of 0.58 reads as
 * "58% relevant" to anybody who has not spent a week with the calibration curve, and this
 * screen is written to be quoted in a dispute.
 *
 * The comfortable failure this file makes red: a classifier that quietly treats a cosine as
 * a plain number, so the rule never fires and the ledger renders raw similarities beside
 * nothing at all.
 */

import { describe, expect, it } from 'vitest';

import {
  arithmeticView,
  classifyKey,
  flattenArithmetic,
} from '../../../src/features/silence/model';
import type { JsonObject } from '../../../src/data/types.generated';

import { sourceSilence } from './_fixture';

const SILENCE = sourceSilence().data;

/** The fixture entry that actually carries channel arithmetic with a cosine in it. */
const SCORED = SILENCE.entries.find(
  (entry) => JSON.stringify(entry.arithmetic).includes('cosine'),
);

describe('the fixture this suite reads is the one it thinks it reads', () => {
  it('carries an entry whose arithmetic contains a raw similarity', () => {
    // Without this the rule below would be exercised only against synthetic blobs, and a
    // classifier that missed the real payload's key names would stay green.
    expect(SCORED).toBeDefined();
  });
});

describe('the classifier', () => {
  it('recognises raw similarity keys, including suffixed ones', () => {
    for (const key of ['cosine', 'similarity', 'dot_product', 'logit', 'fused_raw', 'ann_cosine']) {
      expect(classifyKey(key), key).toBe('raw_similarity');
    }
  });

  it('recognises calibrated keys', () => {
    for (const key of ['p_relevant', 'calibrated', 'p_rel']) {
      expect(classifyKey(key), key).toBe('calibrated');
    }
  });

  it('recognises thresholds, weights, contributions and model identifiers', () => {
    expect(classifyKey('tau')).toBe('threshold');
    expect(classifyKey('theta')).toBe('threshold');
    expect(classifyKey('threshold')).toBe('threshold');
    expect(classifyKey('weight')).toBe('weight');
    expect(classifyKey('contribution')).toBe('contribution');
    expect(classifyKey('embed_model')).toBe('model');
    expect(classifyKey('calibrator')).toBe('model');
  });

  it('leaves everything else plain rather than guessing', () => {
    expect(classifyKey('rule')).toBe('plain');
    expect(classifyKey('bonded')).toBe('plain');
  });
});

describe('flattening', () => {
  it('descends into nested objects and keeps the path', () => {
    const blob: JsonObject = { channels: { ann: { cosine: 0.5 } } };
    const leaves = flattenArithmetic(blob);
    expect(leaves).toHaveLength(1);
    expect(leaves[0]?.path).toEqual(['channels', 'ann', 'cosine']);
    expect(leaves[0]?.pointer).toBe('/channels/ann/cosine');
    expect(leaves[0]?.kind).toBe('raw_similarity');
  });

  it('indexes arrays', () => {
    const leaves = flattenArithmetic({ arms: ['a', 'b'] });
    expect(leaves.map((leaf) => leaf.pointer)).toEqual(['/arms/0', '/arms/1']);
  });

  it('treats an empty container as a leaf rather than dropping it', () => {
    // An empty `channels: {}` is a fact worth seeing: it means the fusion had nothing to
    // fuse. Dropping it would make a degraded run look like a normal one.
    const leaves = flattenArithmetic({ channels: {}, arms: [] });
    expect(leaves.map((leaf) => leaf.pointer).sort()).toEqual(['/arms', '/channels']);
  });

  it('escapes RFC 6901 characters in a key', () => {
    const leaves = flattenArithmetic({ 'a/b~c': 1 });
    expect(leaves[0]?.pointer).toBe('/a~1b~0c');
  });

  it('surfaces the severity-5 threshold as its own row', () => {
    // `tau/severity_5: 0` is the numeric form of "a fatality is always recalled". Burying
    // it inside a collapsed blob would hide the most important number in the ledger.
    if (SCORED === undefined) throw new Error('no scored entry in the fixture');
    const leaves = flattenArithmetic(SCORED.arithmetic);
    const tauLeaves = leaves.filter((leaf) => leaf.path[0] === 'tau');
    expect(tauLeaves.length).toBeGreaterThan(0);
    expect(tauLeaves.every((leaf) => leaf.kind === 'plain' || leaf.kind === 'threshold')).toBe(true);
  });
});

describe('THE RULE — raw similarity is inadmissible without a calibrated value', () => {
  const bare: JsonObject = { channels: { ann: { cosine: 0.58 } } };

  it('refuses a blob with a cosine and no calibrated value anywhere', () => {
    const view = arithmeticView(bare, { score: null, policy_version: null });
    expect(view.rawSimilarities).toHaveLength(1);
    expect(view.calibrated).toBeNull();
    expect(view.rawAdmissible).toBe(false);
  });

  it('admits it once the blob carries p_relevant', () => {
    const view = arithmeticView(
      { ...bare, p_relevant: 0.31 },
      { score: null, policy_version: null },
    );
    expect(view.calibrated).toEqual({ source: 'arithmetic', value: 0.31 });
    expect(view.rawAdmissible).toBe(true);
  });

  it('admits it when the ROW carries the calibrated score instead', () => {
    // `silence_ledger.score` IS the calibrated p_relevant per the DDL. Ignoring it would
    // make the rule fire on correct payloads, and a rule that cries wolf gets deleted.
    const view = arithmeticView(bare, { score: 0.31, policy_version: 'p@1' });
    expect(view.calibrated).toEqual({ source: 'column', value: 0.31 });
    expect(view.rawAdmissible).toBe(true);
  });

  it('is vacuously satisfied when there is no raw similarity at all', () => {
    const view = arithmeticView({ rule: 'deduped against a sibling' }, { score: null, policy_version: null });
    expect(view.rawSimilarities).toEqual([]);
    expect(view.rawAdmissible).toBe(true);
  });

  it('holds on the real fixture entry, and names its calibration commit', () => {
    if (SCORED === undefined) throw new Error('no scored entry in the fixture');
    const view = arithmeticView(SCORED.arithmetic, SCORED);
    expect(view.rawSimilarities.length).toBeGreaterThan(0);
    expect(view.rawAdmissible).toBe(true);
    expect(view.calibrator).not.toBeNull();
    expect(view.policyVersion).toBe(SCORED.policy_version ?? null);
  });

  it('goes inadmissible the moment the calibration is stripped from that same entry', () => {
    // PL-2 in miniature: the rule must be able to fire on the real shape, not only on a
    // hand-made one. Remove p_relevant and the row's score, and the raw values become
    // inadmissible immediately.
    if (SCORED === undefined) throw new Error('no scored entry in the fixture');
    const stripped: JsonObject = Object.fromEntries(
      Object.entries(SCORED.arithmetic).filter(([key]) => key !== 'p_relevant'),
    );
    const view = arithmeticView(stripped, { score: null, policy_version: null });
    expect(view.rawSimilarities.length).toBeGreaterThan(0);
    expect(view.rawAdmissible).toBe(false);
  });
});
