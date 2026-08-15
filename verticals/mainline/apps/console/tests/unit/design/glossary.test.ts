// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE VOCABULARY GATE.
 *
 * `src/design/glossary.ts` claims to carry ruling R7 of
 * `docs/leads/two-audience-ux-plan.md` **verbatim**. A test that counted the entries would
 * pass against a glossary somebody had quietly reworded, so the expected sentences are
 * transcribed here IN FULL, independently, from the ruling. Two transcriptions that agree
 * is evidence; one transcription that counts to nine is not.
 *
 * The rest of the file holds the three properties `done_when` names:
 *
 *   • `docs/console/vocabulary.md` is byte-identical to what `glossary.doc.ts` renders,
 *     the way `doc-generated.test.ts` already holds `visual-language.md` to
 *     `registers.doc.ts`;
 *   • the load-time invariants — unique keys, no empty sentence — actually hold, which is
 *     what the assertion block in `glossary.ts` throws about; and
 *   • no sentence carries one of R7's twelve forbidden words, with the ONE lexical
 *     carve-out pinned to exactly one occurrence so it cannot grow.
 */

import { describe, expect, it } from 'vitest';

import {
  FORBIDDEN_WORDS,
  GLOSSED_TERMS,
  GLOSSED_TERM_KEYS,
  PRODUCT_WORDS,
  PRODUCT_WORD_KEYS,
  SQLSTATE_GLOSSES,
  everySentence,
  forbiddenWordsIn,
  glossFor,
  glossedTerm,
  labelFor,
  productWord,
  sqlstateGloss,
} from '../../../src/design/glossary';
import {
  GENERATED_BLOCKS,
  extractMarkedBlock,
  renderBlock,
  renderMarkedBlock,
} from '../../../src/design/glossary.doc';
import glossarySource from '../../../src/design/glossary.ts?raw';
import doc from '../../../docs/console/vocabulary.md?raw';

// ── R7, transcribed independently ────────────────────────────────────────────────

/** The nine product words: key, the one sentence, the exact thing it names. */
const R7_PRODUCT: readonly (readonly [string, string, string])[] = [
  ['permit', 'A written authorisation for one specific piece of work.', 'mainline.permit'],
  [
    'obligation',
    'Something that must be answered before the permit is allowed to take effect.',
    'mainline.blocking_check',
  ],
  [
    'refusal',
    'The database declining to make the change, and printing its own named reason for it.',
    'a 23514/P0001 error',
  ],
  [
    'signature',
    'One named person recording, under their own credential, how an obligation was answered.',
    'mainline.disposition',
  ],
  [
    'ancestry',
    'The trail from this rule back through the earlier events and edits it came from.',
    'clause_blame_closure + commit_chain',
  ],
  [
    'custody',
    'Proof that a record has not been altered since it was written down.',
    'the ledger + checkpoint',
  ],
  [
    'silence',
    'Everything the search looked at and decided not to show you — and the arithmetic for why.',
    '/v1/permits/{id}/silence',
  ],
  [
    'propagation',
    'Where else the same lesson was applied, and where it was not.',
    '/v1/lessons/{id}/propagation',
  ],
  [
    'synthetic',
    'Made up for this demonstration; corresponds to no real person, site or event.',
    "the seed's own marker",
  ],
];

/** The eighteen glossed terms: key, the label as spelled on screen, the first-use gloss. */
const R7_TERMS: readonly (readonly [string, string, string])[] = [
  [
    'projection',
    'projection / projected counter',
    'A running total the database keeps in a column so a check can be instant instead of re-counting.',
  ],
  [
    'projection-drift',
    'projection drift',
    'When that running total stops matching what the rows actually say — by accident, or on purpose.',
  ],
  [
    'sqlstate',
    'SQLSTATE',
    'The five-character code the database prints to name what it refused. 23514 means a CHECK constraint was not satisfied.',
  ],
  ['constraint', 'constraint', 'A rule written into the table itself, so no query can get around it.'],
  [
    'gate-epoch',
    'gate epoch',
    'A version number for the set of obligations; it moves when they change, so an old signature cannot be reused across the change.',
  ],
  [
    'canonicalisation',
    'canonicalisation',
    'Writing a record in one exact byte-for-byte form, so two different computers hashing it get the same answer. (RFC 8785)',
  ],
  [
    'inclusion-proof',
    'inclusion proof',
    'A short list of hashes that proves one entry really is in the log, without re-reading the log. (RFC 6962)',
  ],
  [
    'consistency-proof',
    'consistency proof',
    'A short list of hashes that proves the log only ever grew, and no earlier entry was rewritten.',
  ],
  [
    'corpus-root',
    'corpus root',
    "The exact commit of the rule-book that this page's ancestry was worked out against.",
  ],
  [
    'clock-skew',
    'clock skew',
    "The server's clock minus this browser's. A screenshot's timestamp means nothing without it.",
  ],
  [
    'minimal-unsatisfiable-subset',
    'minimal unsatisfiable subset',
    'The smallest set of reasons that is on its own enough to cause the refusal — take any one away and it would not refuse.',
  ],
  [
    'nearest-admissible-alternative',
    'nearest admissible alternative',
    'The smallest thing you could actually do that would make this allowed.',
  ],
  [
    'defeater',
    'defeater',
    'The named reason a person is permitted to give for an obligation. The list is fixed per obligation; there is deliberately no general "not applicable".',
  ],
  [
    'virulence',
    'virulence / severity',
    'How bad the underlying failure was, on the scale the record itself carries.',
  ],
  [
    'provenance-chip',
    'provenance chip',
    'The little marker saying how the console came to believe the value beside it — read from a column, recomputed here, or never established.',
  ],
  [
    'staged',
    'STAGED',
    'This value came from a fixture, not from the live database, and the badge is there so you never have to wonder.',
  ],
  [
    'transport',
    'transport',
    'Where these bytes came from: LIVE (a database, just now) or REPLAY (a signed bundle, verified in this browser first).',
  ],
  [
    'seal',
    'seal',
    'Whether this browser re-did the arithmetic over the signed bytes and got the same answer.',
  ],
];

describe('R7 — the product words', () => {
  it('carries exactly nine, in the ruling’s order', () => {
    expect(PRODUCT_WORDS).toHaveLength(9);
    expect(PRODUCT_WORDS.map((entry) => entry.key)).toEqual(R7_PRODUCT.map(([key]) => key));
    expect([...PRODUCT_WORD_KEYS]).toEqual(R7_PRODUCT.map(([key]) => key));
  });

  it.each(R7_PRODUCT)('%s carries R7’s sentence verbatim', (key, sentence, names) => {
    const entry = productWord(key);
    expect(entry, `no product word "${key}"`).not.toBeNull();
    expect(entry?.sentence).toBe(sentence);
    expect(entry?.names).toBe(names);
  });

  it('names an exact database thing for every one of them', () => {
    // The second column is what stops a plain sentence becoming a claim nobody can check.
    for (const entry of PRODUCT_WORDS) {
      expect(entry.names.trim(), `${entry.key} names nothing`).not.toBe('');
    }
  });
});

describe('R7 — the glossed terms', () => {
  it('carries exactly eighteen, in the ruling’s order', () => {
    expect(GLOSSED_TERMS).toHaveLength(18);
    expect(GLOSSED_TERMS.map((entry) => entry.key)).toEqual(R7_TERMS.map(([key]) => key));
    expect([...GLOSSED_TERM_KEYS]).toEqual(R7_TERMS.map(([key]) => key));
  });

  it.each(R7_TERMS)('%s carries R7’s gloss verbatim', (key, label, gloss) => {
    const entry = glossedTerm(key);
    expect(entry, `no glossed term "${key}"`).not.toBeNull();
    expect(entry?.label).toBe(label);
    expect(entry?.gloss).toBe(gloss);
  });

  it('never replaces a term with a simpler word — the label keeps the term’s own spelling', () => {
    // R7's whole point: `minimal unsatisfiable subset` stays `minimal unsatisfiable subset`.
    expect(labelFor('minimal-unsatisfiable-subset')).toBe('minimal unsatisfiable subset');
    expect(labelFor('staged')).toBe('STAGED');
    expect(labelFor('sqlstate')).toBe('SQLSTATE');
  });
});

describe('the SQLSTATE map', () => {
  it('carries the three codes the brief names, verbatim', () => {
    expect(sqlstateGloss('23514')).toBe(
      'a CHECK constraint written into the table was not satisfied',
    );
    expect(sqlstateGloss('P0001')).toBe('a function raised its own named refusal');
    expect(sqlstateGloss('00000')).toBe('the statement succeeded');
  });

  it('covers spec/errors.md’s closed gate-path set, plus 42501 and 00000', () => {
    const codes = SQLSTATE_GLOSSES.map((entry) => entry.code).sort();
    expect(codes).toEqual(['00000', '23503', '23505', '23514', '40001', '42501', 'P0001']);
  });

  it('invents nothing for a code outside the taxonomy', () => {
    // `Sqlstate.tsx` already announces an unmodelled code as unmodelled. A sentence
    // beside it would be the console claiming it understood a refusal nobody modelled.
    expect(sqlstateGloss('99999')).toBeNull();
    expect(sqlstateGloss('')).toBeNull();
  });
});

describe('lookup', () => {
  it('answers for a key in either collection', () => {
    expect(glossFor('permit')).toBe('A written authorisation for one specific piece of work.');
    expect(glossFor('clock-skew')).toContain("The server's clock minus this browser's.");
  });

  it('returns null for an unknown key rather than the key itself', () => {
    // A fallback that rendered the raw slug would put console-composed text in the exact
    // position a reader has been taught to read as a definition.
    expect(glossFor('weld')).toBeNull();
    expect(labelFor('weld')).toBeNull();
    expect(productWord('weld')).toBeNull();
    expect(glossedTerm('permit')).toBeNull();
  });
});

describe('the load-time invariants', () => {
  it('shares no key between the two collections', () => {
    const productKeys: string[] = PRODUCT_WORDS.map((entry) => entry.key);
    const termKeys: string[] = GLOSSED_TERMS.map((entry) => entry.key);
    const keys = [...productKeys, ...termKeys];
    expect(new Set(keys).size, `duplicate key among [${keys.join(', ')}]`).toBe(keys.length);
  });

  it('carries no empty string anywhere', () => {
    const sentences = everySentence();
    expect(sentences.length).toBeGreaterThan(50);
    expect(sentences.filter((sentence) => sentence.trim() === '')).toEqual([]);
  });

  it('declares the assertion at module load, not in a function nobody calls', () => {
    // The invariants above are only worth anything if a violation is refused where it is
    // introduced. `resources.ts` uses the same bare block; this asserts the shape is there.
    expect(glossarySource).toMatch(/glossFor\(\) is a Map lookup/);
    // A bare block at module scope, not a function. `everySentence()` is called inside it,
    // so the empty-string check runs at load rather than when somebody remembers to run it.
    expect(glossarySource).toMatch(/\n\{\n[\s\S]*?everySentence\(\)[\s\S]*?throw new Error/);
  });
});

describe('R7’s forbidden words', () => {
  it('declares the twelve, in the ruling’s order', () => {
    expect([...FORBIDDEN_WORDS]).toEqual([
      'seamless',
      'powerful',
      'robust',
      'enterprise',
      'revolutionary',
      'unlock',
      'empower',
      'leverage',
      'effortless',
      'trust us',
      'simply',
      'just',
    ]);
  });

  it('finds them on a word boundary and not inside a longer word', () => {
    expect(forbiddenWordsIn('a robust, seamless platform')).toEqual(['seamless', 'robust']);
    expect(forbiddenWordsIn('justification, robustness, simplicity')).toEqual([]);
    expect(forbiddenWordsIn('trust  us')).toEqual(['trust us']);
    expect(forbiddenWordsIn('Simply press the button')).toEqual(['simply']);
  });

  it('finds none in any sentence the vocabulary carries', () => {
    const offenders = everySentence()
      .map((sentence) => [sentence, forbiddenWordsIn(sentence)] as const)
      .filter(([, hits]) => hits.length > 0)
      .map(([sentence, hits]) => `${hits.join(', ')} in "${sentence}"`);
    expect(
      offenders,
      'R7: every one of these lets a sentence describe an effect on the reader instead of a ' +
        'fact about a field. The test for an added sentence is: can I point at the field it ' +
        'came from?',
    ).toEqual([]);
  });

  it('applies the "just now" carve-out EXACTLY once across the whole vocabulary', () => {
    // R7's own `transport` gloss says "LIVE (a database, just now)", where `just` is a time
    // reference rather than the minimiser the ruling bans. That text is normative and copied
    // verbatim, so the gate distinguishes the two senses lexically. Pinned at one: a second
    // occurrence is a failure, and the fix is to write the sentence differently rather than
    // to widen the exception.
    const all = everySentence().join(' ');
    expect(all.match(/\bjust now\b/gi) ?? []).toHaveLength(1);
    expect(
      all.match(/\bjust\b/gi) ?? [],
      'a `just` that is not `just now` is the minimiser R7 bans',
    ).toHaveLength(1);
  });
});

describe('docs/console/vocabulary.md', () => {
  it.each([...GENERATED_BLOCKS])('carries the generated `%s` block, unedited', (block) => {
    const found = extractMarkedBlock(doc, block);
    expect(
      found,
      `the ${block} markers are missing or out of order in docs/console/vocabulary.md. A ` +
        'generated table nobody can find is a table that stopped being checked.',
    ).not.toBeNull();

    const expected = renderBlock(block);
    expect(
      found,
      `docs/console/vocabulary.md's ${block} block has drifted from src/design/glossary.ts.\n\n` +
        `Replace the block with exactly:\n\n${renderMarkedBlock(block)}\n`,
    ).toBe(expected);
  });

  it('mentions every product word and every term label', () => {
    for (const entry of PRODUCT_WORDS) {
      expect(doc, `${entry.key} is absent from the document`).toContain(entry.key);
    }
    for (const entry of GLOSSED_TERMS) {
      expect(doc, `${entry.label} is absent from the document`).toContain(entry.label);
    }
  });

  it('says the document is generated and that editing it turns CI red', () => {
    expect(doc).toContain('src/design/glossary.ts');
    expect(doc).toContain('Do not edit by hand');
    expect(doc.toLowerCase()).toContain('generated');
  });

  it('records the two headings R7 overrules, so nothing is lost silently', () => {
    expect(doc).toContain('The weld');
    expect(doc).toContain('What the database checks before it will merge');
    expect(doc).toContain('Irreducible reason set');
    expect(doc).toContain('Why it refused — the smallest set of reasons');
  });

  it('states the one carve-out rather than leaving it to be discovered', () => {
    expect(doc).toContain('just now');
    expect(doc).toContain('exactly once');
  });
});

describe('the renderer itself', () => {
  it('produces a row for every entry', () => {
    const words = renderBlock('product-words');
    for (const entry of PRODUCT_WORDS) expect(words).toContain(`**${entry.key}**`);
    const terms = renderBlock('glossed-terms');
    for (const entry of GLOSSED_TERMS) expect(terms).toContain(`\`${entry.label}\``);
    const codes = renderBlock('sqlstates');
    for (const entry of SQLSTATE_GLOSSES) expect(codes).toContain(`\`${entry.code}\``);
  });

  it('keeps every data row at the header’s column count', () => {
    for (const block of GENERATED_BLOCKS) {
      const lines = renderBlock(block).split('\n');
      const columns = (lines[0] ?? '').split('|').length;
      for (const line of lines.slice(2)) {
        expect(line.split('|').length, `${block}: ${line}`).toBe(columns);
      }
    }
  });

  it('round-trips: what it renders is what it extracts', () => {
    for (const block of GENERATED_BLOCKS) {
      const marked = renderMarkedBlock(block);
      expect(extractMarkedBlock(`prefix\n\n${marked}\n\nsuffix`, block)).toBe(renderBlock(block));
    }
  });

  it('returns null when a marker is missing rather than silently passing', () => {
    expect(extractMarkedBlock('no markers here', 'product-words')).toBeNull();
  });
});

describe('the shipped closure', () => {
  it('keeps the Markdown renderer out of it', () => {
    // `glossary.ts` is statically reachable from the evidentiary shell, whose gzip closure
    // budgets.json caps at 225 280 bytes with required: true. The tables around the
    // sentences are a build-time artefact and would be a second copy of the same prose.
    // Comments are stripped first: the header must go on NAMING glossary.doc.ts, so the
    // next reader finds the renderer; what it must not do is depend on it.
    const code = glossarySource.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
    expect(code).not.toContain('glossary.doc');
  });

  it('imports nothing at all, so it cannot drag a dependency into the shell', () => {
    const imports = glossarySource
      .split('\n')
      .filter((line) => /^\s*import\s/.test(line));
    expect(imports, `glossary.ts imports ${imports.join(' / ')}`).toEqual([]);
  });
});
