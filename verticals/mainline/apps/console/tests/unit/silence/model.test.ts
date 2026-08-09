// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The silence model: the conservation identity, the bonded invariant, the score rule, the
 * PER boundary and the ordering.
 *
 * Every assertion is written so the COMFORTABLE failure is red — an identity that reports
 * "balanced" without adding anything up, a score rendered bare because its threshold was
 * missing, a boundary pair accepted without bracketing theta, an ordering that hides the
 * near-misses at the bottom.
 */

import { describe, expect, it } from 'vitest';

import {
  bondedOf,
  boundaryPairOf,
  boundarySane,
  compareSilenceEntries,
  conservationOf,
  PER_LIMIT_SENTENCE,
  scoreDisplay,
  tally,
} from '../../../src/features/silence/model';
import type { RecallRun, SilenceEntry } from '../../../src/data/types.generated';

import { sourceRecallRun, sourceSilence } from './_fixture';

const RUN: RecallRun = sourceRecallRun().data;
const SILENCE = sourceSilence().data;

describe('the fixture this suite reads is the one it thinks it reads', () => {
  it('carries counts, a receipt and at least one scored entry', () => {
    expect(RUN.counts.n_candidates).toBeGreaterThan(0);
    expect(SILENCE.receipt).not.toBeNull();
    expect(SILENCE.entries.length).toBeGreaterThan(0);
    expect(SILENCE.entries.some((entry) => (entry.score ?? null) !== null)).toBe(true);
  });
});

describe('candidates_conserved — the identity the reader adds up', () => {
  const identity = conservationOf(RUN);

  it('names the constraint the database enforces', () => {
    expect(identity.constraint).toBe('candidates_conserved');
  });

  it('actually adds the four terms rather than restating n_candidates', () => {
    // The failure this guards: a `sum` that returned `n_candidates` would make `balances`
    // permanently true and the panel permanently meaningless.
    const byHand =
      RUN.counts.n_blocking + RUN.counts.n_advisory + RUN.counts.n_silenced + RUN.counts.n_deduped;
    expect(identity.sum).toBe(byHand);
    expect(identity.terms.map((term) => term.column)).toEqual([
      'n_blocking',
      'n_advisory',
      'n_silenced',
      'n_deduped',
    ]);
  });

  it('balances on the fixture, with a zero residual', () => {
    expect(identity.balances).toBe(true);
    expect(identity.residual).toBe(0);
  });

  it('reports an imbalance rather than rounding it away', () => {
    const broken: RecallRun = { ...RUN, counts: { ...RUN.counts, n_silenced: RUN.counts.n_silenced + 1 } };
    const wrong = conservationOf(broken);
    expect(wrong.balances).toBe(false);
    expect(wrong.residual).toBe(-1);
  });
});

describe('bonded_fatalities_all_blocking — a fatality is always recalled', () => {
  it('is an equality between two columns, named by its constraint', () => {
    const bonded = bondedOf(RUN);
    expect(bonded.constraint).toBe('bonded_fatalities_all_blocking');
    expect(bonded.bonded.column).toBe('n_bonded_sev5');
    expect(bonded.blocking.column).toBe('n_bonded_sev5_blocking');
    expect(bonded.holds).toBe(RUN.counts.n_bonded_sev5 === RUN.counts.n_bonded_sev5_blocking);
  });

  it('goes false when one bonded fatality is not blocking', () => {
    const broken: RecallRun = {
      ...RUN,
      counts: { ...RUN.counts, n_bonded_sev5_blocking: RUN.counts.n_bonded_sev5 - 1 },
    };
    expect(bondedOf(broken).holds).toBe(false);
  });
});

// ── The score rule ─────────────────────────────────────────────────────────

function entryWith(overrides: Partial<SilenceEntry>): SilenceEntry {
  const base = SILENCE.entries[0];
  if (base === undefined) throw new Error('the fixture carries no silence entry');
  return { ...base, ...overrides };
}

describe('a score is never displayable alone', () => {
  it('shows a score that has both its threshold and its policy version', () => {
    const display = scoreDisplay(
      entryWith({ score: 0.31, threshold: 0.45, policy_version: 'p@1' }),
    );
    expect(display.kind).toBe('shown');
    if (display.kind === 'shown') {
      expect(display.score).toBe(0.31);
      expect(display.threshold).toBe(0.45);
      expect(display.policyVersion).toBe('p@1');
      expect(display.atOrAboveThreshold).toBe(false);
    }
  });

  it('WITHHOLDS a score whose threshold is missing, and names what is missing', () => {
    const display = scoreDisplay(entryWith({ score: 0.31, threshold: null, policy_version: 'p@1' }));
    expect(display.kind).toBe('withheld');
    if (display.kind === 'withheld') expect(display.missing).toEqual(['threshold']);
  });

  it('WITHHOLDS a score whose policy version is missing', () => {
    const display = scoreDisplay(entryWith({ score: 0.31, threshold: 0.45, policy_version: null }));
    expect(display.kind).toBe('withheld');
    if (display.kind === 'withheld') expect(display.missing).toEqual(['policy_version']);
  });

  it('names BOTH when both are missing', () => {
    const display = scoreDisplay(entryWith({ score: 0.31, threshold: null, policy_version: null }));
    expect(display.kind).toBe('withheld');
    if (display.kind === 'withheld') expect(display.missing).toEqual(['threshold', 'policy_version']);
  });

  it('treats an empty policy version as missing, not as present-but-blank', () => {
    const display = scoreDisplay(entryWith({ score: 0.31, threshold: 0.45, policy_version: '' }));
    expect(display.kind).toBe('withheld');
  });

  it('reports absence as absence when there is no score at all', () => {
    expect(scoreDisplay(entryWith({ score: null })).kind).toBe('absent');
  });

  it('every scored row in the fixture is displayable — the payload keeps its own rule', () => {
    for (const entry of SILENCE.entries) {
      if ((entry.score ?? null) === null) continue;
      expect(
        scoreDisplay(entry).kind,
        `entry ${entry.silence_id} carries a score with no threshold or no policy_version`,
      ).toBe('shown');
    }
  });
});

// ── PER ────────────────────────────────────────────────────────────────────

describe('the PER commitment', () => {
  const receipt = SILENCE.receipt;

  it('states its limit as a constant a CI grep can find', () => {
    expect(PER_LIMIT_SENTENCE).toContain('exhaustion of the retrieval that ran');
    expect(PER_LIMIT_SENTENCE).toContain('not of the corpus');
  });

  it('brackets theta with the disclosed pair', () => {
    if (receipt === null) throw new Error('no receipt in the fixture');
    const pair = boundaryPairOf(receipt);
    expect(pair.theta).toBe(receipt.theta);
    expect(pair.atS.score).toBeGreaterThanOrEqual(receipt.theta);
    expect(pair.bracketsTheta).toBe(true);
  });

  it('refuses to call a non-bracketing pair a bracket', () => {
    if (receipt === null) throw new Error('no receipt in the fixture');
    const broken = boundaryPairOf({ ...receipt, theta: receipt.theta + 10 });
    expect(broken.bracketsTheta).toBe(false);
  });

  it('treats a missing s+1 as the boundary sitting at the end, not as a gap', () => {
    if (receipt === null) throw new Error('no receipt in the fixture');
    const atEnd = boundaryPairOf({
      ...receipt,
      boundary_proof: { ...receipt.boundary_proof, leaf_s_plus_1: null },
    });
    expect(atEnd.boundaryAtEnd).toBe(true);
    expect(atEnd.atSPlusOne).toBeNull();
    expect(atEnd.bracketsTheta).toBe(true);
  });

  it('checks boundary_sane the way the CHECK constraint does', () => {
    if (receipt === null) throw new Error('no receipt in the fixture');
    expect(boundarySane(receipt)).toBe(true);
    expect(boundarySane({ ...receipt, s: receipt.n + 1 })).toBe(false);
    expect(boundarySane({ ...receipt, s: -1 })).toBe(false);
  });
});

// ── Ordering and tallies ───────────────────────────────────────────────────

describe('ordering', () => {
  const make = (severity: number, score: number | null, id: string): SilenceEntry =>
    entryWith({ severity, score, silence_id: id });

  it('puts higher severity first', () => {
    const rows = [make(2, 0.9, 'a'), make(5, 0.1, 'b')].sort(compareSilenceEntries);
    expect(rows.map((row) => row.silence_id)).toEqual(['b', 'a']);
  });

  it('within a band, puts the NEAREST MISS first', () => {
    const rows = [make(3, 0.1, 'far'), make(3, 0.44, 'near')].sort(compareSilenceEntries);
    expect(rows.map((row) => row.silence_id)).toEqual(['near', 'far']);
  });

  it('sorts unscored rows after scored ones within a band, deterministically', () => {
    const rows = [make(3, null, 'z'), make(3, 0.2, 'y'), make(3, null, 'a')].sort(
      compareSilenceEntries,
    );
    expect(rows.map((row) => row.silence_id)).toEqual(['y', 'a', 'z']);
  });

  it('is independent of input order', () => {
    const forward = [make(3, 0.2, 'a'), make(4, 0.1, 'b'), make(3, null, 'c')].sort(
      compareSilenceEntries,
    );
    const backward = [make(3, null, 'c'), make(4, 0.1, 'b'), make(3, 0.2, 'a')].sort(
      compareSilenceEntries,
    );
    expect(forward.map((row) => row.silence_id)).toEqual(backward.map((row) => row.silence_id));
  });
});

describe('the census', () => {
  it('counts every row exactly once, by source and by reason', () => {
    const bySource = tally(SILENCE.entries, 'source');
    const byReason = tally(SILENCE.entries, 'reason');
    const total = (rows: readonly (readonly [string, number])[]): number =>
      rows.reduce((sum, [, count]) => sum + count, 0);
    expect(total(bySource)).toBe(SILENCE.entries.length);
    expect(total(byReason)).toBe(SILENCE.entries.length);
  });

  it('is deterministic — count descending, then the vocabulary term', () => {
    const rows = tally(
      [
        entryWith({ source: 'dedup', silence_id: '1' }),
        entryWith({ source: 'recall', silence_id: '2' }),
        entryWith({ source: 'recall', silence_id: '3' }),
      ],
      'source',
    );
    expect(rows).toEqual([
      ['recall', 2],
      ['dedup', 1],
    ]);
  });
});
