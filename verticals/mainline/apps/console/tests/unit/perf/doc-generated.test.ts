// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * `docs/performance-budgets.md` is RENDERED FROM `src/perf/`, not written beside it.
 *
 * A performance document that has drifted from the numbers the gate enforces is worse than
 * no document, because it is the version somebody quotes. The committed file is
 * byte-identical to the renderer or CI is red.
 */

import { describe, expect, it } from 'vitest';

import {
  GENERATED_BLOCKS,
  extractMarkedBlock,
  renderBlock,
  renderMarkedBlock,
} from '../../../src/perf/budgets.doc';
import { BUDGETS, formatLimit } from '../../../src/perf/budgets';
import { SPANS } from '../../../src/perf/marks';
import doc from '../../../docs/performance-budgets.md?raw';

describe('docs/performance-budgets.md', () => {
  it.each([...GENERATED_BLOCKS])('carries the generated `%s` block, unedited', (block) => {
    const found = extractMarkedBlock(doc, block);
    expect(
      found,
      `the ${block} markers are missing or out of order in docs/performance-budgets.md.`,
    ).not.toBeNull();

    expect(
      found,
      `docs/performance-budgets.md's ${block} block has drifted from src/perf/.\n\n` +
        `Replace the block with exactly:\n\n${renderMarkedBlock(block)}\n`,
    ).toBe(renderBlock(block));
  });

  it('names every budget, its limit and the conditions it is only true under', () => {
    for (const budget of BUDGETS) {
      expect(doc, `${budget.id} is absent`).toContain(budget.id);
      expect(doc, `${budget.id}'s limit is absent`).toContain(formatLimit(budget));
      expect(doc, `${budget.id}'s conditions are absent`).toContain(budget.conditions);
    }
  });

  it('names every span', () => {
    for (const span of SPANS) expect(doc).toContain(span.id);
  });

  it('states the percentile method, because a p95 without one is not a number', () => {
    expect(doc).toContain('NEAREST RANK');
    expect(doc).toContain('ceil(p × n)');
    expect(doc).toContain('Below 20 samples it returns `null`, not the maximum.');
  });

  it('says out loud that a missing measurement is not a pass', () => {
    expect(doc).toContain('A console with no instrumentation at all passes every budget it has.');
    expect(doc).toContain('a gate that did not run has not passed');
  });

  it('prints the unmeasurable status in bold and names who owes the tier', () => {
    expect(doc).toContain('**NOT YET MEASURABLE**');
    expect(doc).toContain('cinema-conformance-harness');
    expect(doc).toContain('tests/browser/budgets.spec.ts');
  });

  it('records that verification is deliberately un-budgeted', () => {
    // A number here that made the in-browser verifier look slow would create pressure to
    // check less, which is the one direction this console must never be pushed.
    expect(doc).toContain('deliberately un-budgeted');
    expect(doc).toContain('honesty, not latency');
  });
});
