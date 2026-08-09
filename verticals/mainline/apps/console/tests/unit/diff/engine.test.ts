// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE TEXT ENGINE — written RED, before `src/features/diff/engine/` existed.
 *
 * The clause diff is the one place in this console where the browser computes something
 * that is then shown beside a database claim. That is only defensible if the computation
 * is TOTAL and LOSSLESS: every character of both `canon_text` values must appear in the
 * segment list, in order, exactly once. A renderer that silently drops a clause of a
 * procedure while showing a reassuring "1 change" header is the exact failure this whole
 * product exists to make impossible, and it is invisible to an eyeball review.
 *
 * So the load-bearing assertion here is not "the diff looks right". It is:
 *
 *     concat(segments where kind ∈ {equal, removed}) === parent.canon_text
 *     concat(segments where kind ∈ {equal, added})   === version.canon_text
 *
 * checked over every pair in this file, including the degraded path. If the diff budget
 * is exhausted the engine must still satisfy both equations — a degradation that loses
 * text is a lie, and "we ran out of budget" is not an excuse a court accepts.
 */

import { describe, expect, it } from 'vitest';

import { diffCanonText, MAX_DIFF_CELLS } from '../../../src/features/diff/engine/text-diff';
import { tokenise } from '../../../src/features/diff/engine/tokenise';
import type { TextDiff } from '../../../src/features/diff/model';

const PARENT =
  'Before any intrusive work on a drive assembly, the electrical supply shall be isolated ' +
  'and locked out, and residual stored energy shall be verified as zero at every accumulator ' +
  'in the isolated circuit. Verification shall be recorded on the permit by the isolating ' +
  'officer and countersigned by the responsible engineer.';

const VERSION =
  'Before any intrusive work on a drive assembly, the electrical supply shall be isolated ' +
  'and locked out, and residual stored energy shall be verified as zero at the hydraulic ' +
  'power unit. Verification shall be recorded on the permit by the isolating officer.';

function reassembleFrom(diff: TextDiff): string {
  return diff.segments
    .filter((segment) => segment.kind !== 'added')
    .map((segment) => segment.text)
    .join('');
}

function reassembleTo(diff: TextDiff): string {
  return diff.segments
    .filter((segment) => segment.kind !== 'removed')
    .map((segment) => segment.text)
    .join('');
}

const PAIRS: readonly (readonly [string, string, string])[] = [
  ['identical', PARENT, PARENT],
  ['the demonstration edit', PARENT, VERSION],
  ['the demonstration edit, reversed', VERSION, PARENT],
  ['insertion at the end', 'shall be isolated', 'shall be isolated and locked out'],
  ['deletion at the start', 'The officer shall verify.', 'shall verify.'],
  ['empty parent', '', 'a new clause'],
  ['empty version', 'a retired clause', ''],
  ['both empty', '', ''],
  ['whitespace only change', 'a  b', 'a b'],
  ['single character', 'a', 'b'],
  ['punctuation only', 'zero at the unit.', 'zero at the unit;'],
  ['unicode', 'isolate ≥ 2 accumulators — verify', 'isolate ≥ 1 accumulator — verify'],
];

describe('tokenise — the offsets a highlight is drawn against', () => {
  it('reproduces the input exactly when the tokens are concatenated', () => {
    for (const [name, from, to] of PAIRS) {
      for (const text of [from, to]) {
        const tokens = tokenise(text);
        expect(tokens.map((token) => token.text).join(''), name).toBe(text);
      }
    }
  });

  it('emits contiguous offsets starting at zero', () => {
    const tokens = tokenise(PARENT);
    let cursor = 0;
    for (const token of tokens) {
      expect(token.start).toBe(cursor);
      expect(token.end).toBe(cursor + token.text.length);
      expect(token.end).toBeGreaterThan(token.start);
      cursor = token.end;
    }
    expect(cursor).toBe(PARENT.length);
  });

  it('separates words, whitespace and punctuation so a one-word edit is one token', () => {
    const tokens = tokenise('zero at the unit.');
    expect(tokens.map((token) => token.text)).toEqual([
      'zero',
      ' ',
      'at',
      ' ',
      'the',
      ' ',
      'unit',
      '.',
    ]);
    expect(tokens.map((token) => token.kind)).toEqual([
      'word',
      'space',
      'word',
      'space',
      'word',
      'space',
      'word',
      'punct',
    ]);
  });

  it('emits nothing for the empty string rather than one empty token', () => {
    expect(tokenise('')).toEqual([]);
  });
});

describe('diffCanonText — the loss-free property', () => {
  it('reassembles both sides exactly, for every pair', () => {
    for (const [name, from, to] of PAIRS) {
      const diff = diffCanonText(from, to);
      expect(reassembleFrom(diff), `${name}: parent side`).toBe(from);
      expect(reassembleTo(diff), `${name}: version side`).toBe(to);
    }
  });

  it('reports identical texts as identical, with no removed or added characters', () => {
    const diff = diffCanonText(PARENT, PARENT);
    expect(diff.identical).toBe(true);
    expect(diff.removedChars).toBe(0);
    expect(diff.addedChars).toBe(0);
    expect(diff.segments.every((segment) => segment.kind === 'equal')).toBe(true);
  });

  it('does not report a change as identical when only whitespace moved', () => {
    const diff = diffCanonText('a  b', 'a b');
    expect(diff.identical).toBe(false);
  });

  it('carries offsets into the correct side, and null on the side a segment is absent from', () => {
    const diff = diffCanonText('the responsible engineer', 'the isolating engineer');
    for (const segment of diff.segments) {
      if (segment.kind === 'equal') {
        expect(segment.fromStart).not.toBeNull();
        expect(segment.toStart).not.toBeNull();
      }
      if (segment.kind === 'removed') {
        expect(segment.fromStart).not.toBeNull();
        expect(segment.toStart).toBeNull();
      }
      if (segment.kind === 'added') {
        expect(segment.fromStart).toBeNull();
        expect(segment.toStart).not.toBeNull();
      }
    }
    const removed = diff.segments.filter((segment) => segment.kind === 'removed');
    const added = diff.segments.filter((segment) => segment.kind === 'added');
    expect(removed.map((segment) => segment.text).join('')).toBe('responsible');
    expect(added.map((segment) => segment.text).join('')).toBe('isolating');
  });

  it('slices the recorded offsets back out of the original strings', () => {
    const diff = diffCanonText(PARENT, VERSION);
    for (const segment of diff.segments) {
      if (segment.fromStart !== null && segment.fromEnd !== null) {
        expect(PARENT.slice(segment.fromStart, segment.fromEnd)).toBe(segment.text);
      }
      if (segment.toStart !== null && segment.toEnd !== null) {
        expect(VERSION.slice(segment.toStart, segment.toEnd)).toBe(segment.text);
      }
    }
  });

  it('never emits two adjacent segments of the same kind', () => {
    const diff = diffCanonText(PARENT, VERSION);
    for (let i = 1; i < diff.segments.length; i += 1) {
      expect(diff.segments[i]?.kind).not.toBe(diff.segments[i - 1]?.kind);
    }
  });

  it('is deterministic — the same inputs produce a byte-identical model', () => {
    const first = JSON.stringify(diffCanonText(PARENT, VERSION));
    const second = JSON.stringify(diffCanonText(PARENT, VERSION));
    expect(first).toBe(second);
  });

  it('counts characters, not tokens, and the counts agree with the segments', () => {
    const diff = diffCanonText(PARENT, VERSION);
    const removed = diff.segments
      .filter((segment) => segment.kind === 'removed')
      .reduce((total, segment) => total + segment.text.length, 0);
    const added = diff.segments
      .filter((segment) => segment.kind === 'added')
      .reduce((total, segment) => total + segment.text.length, 0);
    expect(diff.removedChars).toBe(removed);
    expect(diff.addedChars).toBe(added);
    expect(diff.parentLength).toBe(PARENT.length);
    expect(diff.versionLength).toBe(VERSION.length);
  });
});

describe('diffCanonText — degradation is declared, never silent', () => {
  /**
   * Two texts with no common prefix, no common suffix and enough tokens to blow any
   * sane budget. The engine must refuse to compute a token-level diff and say so —
   * and it must STILL reproduce both texts, because a reader who cannot reassemble the
   * clause from the screen has been shown a summary, not an exhibit.
   */
  const longFrom = Array.from({ length: 400 }, (_, i) => `alpha${i}`).join(' ');
  const longTo = Array.from({ length: 400 }, (_, i) => `omega${i}`).join(' ');

  it('degrades with a named reason when the budget cannot cover the pair', () => {
    const diff = diffCanonText(longFrom, longTo, { maxCells: 64 });
    expect(diff.degraded).not.toBeNull();
    expect(diff.degraded?.reason).toBe('diff_budget_exhausted');
    expect(diff.degraded?.budget).toBe(64);
    expect(diff.degraded?.demanded).toBeGreaterThan(64);
  });

  it('reassembles both sides exactly even when degraded', () => {
    const diff = diffCanonText(longFrom, longTo, { maxCells: 64 });
    expect(reassembleFrom(diff)).toBe(longFrom);
    expect(reassembleTo(diff)).toBe(longTo);
  });

  it('does not degrade at the default budget for a clause-sized edit', () => {
    expect(diffCanonText(PARENT, VERSION).degraded).toBeNull();
    // A clause is capped at 65 536 characters by the contract. The default budget must
    // leave a realistic edit — one whose differing middle is a few hundred tokens —
    // exact, or the degraded path becomes the normal path and nobody reads the notice.
    expect(MAX_DIFF_CELLS).toBeGreaterThanOrEqual(1_000_000);
  });

  it('trims the common prefix and suffix before spending budget', () => {
    // Identical except for one word in the middle: the trimmed middle is tiny, so a
    // budget far below `length × length` must still produce an exact diff.
    const diff = diffCanonText(PARENT, VERSION, { maxCells: 4096 });
    expect(diff.degraded).toBeNull();
    expect(reassembleFrom(diff)).toBe(PARENT);
    expect(reassembleTo(diff)).toBe(VERSION);
  });
});
