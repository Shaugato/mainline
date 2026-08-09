// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * `docs/accessibility.md` is RENDERED FROM the code, not written beside it.
 *
 * The failure mode of every accessibility document that has ever shipped: the document and
 * the implementation agree on the day they are written and diverge on every day after. It
 * matters more here than in a design system, because this is the document somebody quotes
 * in a procurement answer or a court filing — and a stale claim there is a claim made
 * about a control that no longer exists.
 *
 * There is no generator script. A pure renderer plus a refusing test cannot drift: the
 * committed document is byte-identical to `renderMarkedBlock()` or CI is red, and the
 * failure message is the exact text to paste.
 */

import { describe, expect, it } from 'vitest';

import {
  GENERATED_BLOCKS,
  extractMarkedBlock,
  renderBlock,
  renderMarkedBlock,
} from '../../../src/a11y/contract.doc';
import { A11Y_LAW, KEYBOARD_TRAVERSAL, SURFACE_OPERATIONS } from '../../../src/a11y/contract';
import { NOT_CHECKED_HERE, RULE_IDS } from '../../../src/a11y/audit';
import doc from '../../../docs/accessibility.md?raw';

describe('docs/accessibility.md', () => {
  it.each([...GENERATED_BLOCKS])('carries the generated `%s` block, unedited', (block) => {
    const found = extractMarkedBlock(doc, block);
    expect(
      found,
      `the ${block} markers are missing or out of order in docs/accessibility.md. A generated ` +
        'table nobody can find is a table that stopped being checked.',
    ).not.toBeNull();

    expect(
      found,
      `docs/accessibility.md's ${block} block has drifted from the code.\n\n` +
        `Replace the block with exactly:\n\n${renderMarkedBlock(block)}\n`,
    ).toBe(renderBlock(block));
  });

  it('mentions every law, every rule, every traversal step and every surface', () => {
    for (const law of A11Y_LAW) expect(doc, `${law.id} is absent`).toContain(law.id);
    for (const ruleId of RULE_IDS) expect(doc, `${ruleId} is absent`).toContain(ruleId);
    for (const step of KEYBOARD_TRAVERSAL) expect(doc).toContain(step.id);
    for (const entry of SURFACE_OPERATIONS) expect(doc).toContain(`\`${entry.surface}\``);
  });

  it('prints the unmeasured coverage state in bold rather than quietly', () => {
    // The coverage column is what a reader skims. A document that rendered "browser-tier"
    // as a lowercase word would undo in one glance what contract.ts spends a file saying.
    expect(doc).toContain('**NOT YET MEASURED** (browser tier)');
  });

  it('states, in the document itself, what NO tier in this repository checks', () => {
    expect(doc).toContain('What NO tier in this repository checks today');
    // Each honest limit the auditor reports must be findable in the document, so the two
    // cannot disagree about the size of the gap.
    for (const subject of ['Colour contrast', 'Target size', 'Reflow', 'Reading order']) {
      expect(doc, `${subject} is missing from the limits section`).toContain(subject);
    }
    expect(NOT_CHECKED_HERE.length).toBeGreaterThan(5);
  });

  it('claims no conformance', () => {
    // WCAG criteria are cited as vocabulary. Citing a criterion is not meeting it, and
    // the disclaimer must be PRESENT — a silent omission reads as an oversight.
    expect(doc).toContain('No conformance claim is made anywhere in this repository');
    expect(doc).not.toContain('WCAG 2.2 AA compliant');
    expect(doc).not.toContain('fully accessible');
  });

  it('names the worker who owns the tier that has not landed', () => {
    expect(doc).toContain('cinema-conformance-harness');
    expect(doc).toContain('tests/browser/a11y.spec.ts');
  });
});
