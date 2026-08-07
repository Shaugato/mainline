// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * `docs/visual-language.md`'s tables are RENDERED FROM `registers.ts`, not written
 * beside it.
 *
 * The `visual-language` worker's `done_when` requires it, and the reason is the failure
 * mode of every design system that has ever shipped: the document and the code agree on
 * the day they are written and diverge on every day after. A register added to the code
 * and not to the document is a register nobody knows the law for; a token added to the
 * document and not to the code is a promise the build does not keep.
 *
 * ── WHY A CHECK RATHER THAN A WRITER ─────────────────────────────────────────────
 *
 * There is no `scripts/gen-docs.ts` here. A generator needs `node:fs`, which this
 * workspace's application tsconfig deliberately cannot see (Node globals must not be
 * reachable from browser code), and `scripts/` is allocated file-by-file to other
 * workers. More to the point, a generator that runs when somebody remembers to run it is
 * a documentation process; a pure renderer plus a refusing test is a gate. The document
 * is either byte-identical to `renderMarkedBlock()` or CI is red, and the failure
 * message is the exact text to paste.
 */

import { describe, expect, it } from 'vitest';

import {
  GENERATED_BLOCKS,
  extractMarkedBlock,
  renderBlock,
  renderMarkedBlock,
} from '../../../src/design/registers.doc';
import { REGISTER_LAW, TOKEN_LAW } from '../../../src/design/registers';
import doc from '../../../docs/visual-language.md?raw';

describe('docs/visual-language.md', () => {
  it.each([...GENERATED_BLOCKS])('carries the generated `%s` block, unedited', (block) => {
    const found = extractMarkedBlock(doc, block);
    expect(
      found,
      `the ${block} markers are missing or out of order in docs/visual-language.md. A generated ` +
        'table nobody can find is a table that stopped being checked.',
    ).not.toBeNull();

    const expected = renderBlock(block);
    expect(
      found,
      `docs/visual-language.md's ${block} block has drifted from src/design/registers.ts.\n\n` +
        `Replace the block with exactly:\n\n${renderMarkedBlock(block)}\n`,
    ).toBe(expected);
  });

  it('mentions every register by label', () => {
    for (const law of REGISTER_LAW) {
      expect(doc).toContain(law.label);
    }
  });

  it('mentions every token, because the generated table contains all of them', () => {
    for (const rule of TOKEN_LAW) {
      expect(doc, `${rule.token} is absent from the document`).toContain(rule.token);
    }
  });

  it('states the APCA floors as ratchets and claims no conformance', () => {
    // pairs.ts sets APCA floors as ratchets, not as a conformance claim. Asserting
    // conformance in the spec would be the exact kind of unearned claim this console
    // exists to refuse — and the disclaimer has to be PRESENT, not merely the claim
    // absent, because a silent omission reads as an oversight.
    expect(doc).toContain('APCA');
    expect(doc.toLowerCase()).toContain('ratchet');
    expect(doc.toLowerCase()).not.toMatch(/\b(conforms? to|conformant with|compliant with|meets) apca/);
    expect(doc.toLowerCase()).not.toMatch(/apca[- ]w3 (bronze|silver) (conformance|conformant|compliant)\b/);
  });
});

describe('the renderer itself', () => {
  it('produces a table row for every register and every token', () => {
    const registers = renderBlock('registers');
    for (const law of REGISTER_LAW) {
      expect(registers).toContain(`**${law.label}**`);
    }
    const tokens = renderBlock('tokens');
    for (const rule of TOKEN_LAW) {
      expect(tokens).toContain(`\`${rule.token}\``);
    }
  });

  it('marks a register that may not use a token with a refusal, not a blank', () => {
    const tokens = renderBlock('tokens');
    // `--tp-ok` is EVIDENCE-only. A blank cell reads as an oversight; `·` reads as a rule.
    const row = tokens.split('\n').find((line) => line.includes('`--tp-ok`'));
    expect(row).toBeDefined();
    expect(row).toContain('✓');
    expect(row).toContain('·');
  });

  it('escapes a pipe so a purpose string cannot break the table', () => {
    const laws = renderBlock('register-laws');
    expect(laws).toContain('THE STILLNESS RULE');
    const registers = renderBlock('registers');
    for (const line of registers.split('\n').slice(2)) {
      // Every data row must have the same column count as the header.
      expect(line.split('|').length).toBe(8);
    }
  });

  it('round-trips: what it renders is what it extracts', () => {
    for (const block of GENERATED_BLOCKS) {
      const marked = renderMarkedBlock(block);
      expect(extractMarkedBlock(`prefix\n\n${marked}\n\nsuffix`, block)).toBe(renderBlock(block));
    }
  });

  it('returns null when a marker is missing rather than silently passing', () => {
    expect(extractMarkedBlock('no markers here', 'registers')).toBeNull();
  });
});
