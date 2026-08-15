// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * `docs/console/vocabulary.md`'s tables, GENERATED from `glossary.ts`.
 *
 * The same arrangement `registers.doc.ts` and `a11y/contract.doc.ts` already use, and for
 * the same reason: the spec and the implementation are one object. A word added to the
 * code and not to the document is a word nobody can look up; a word in the document that
 * the code has never heard of is a promise the console does not keep.
 *
 * ── WHY A CHECK RATHER THAN A WRITER ─────────────────────────────────────────────
 *
 * There is no filesystem access here, for the reason `registers.doc.ts` states: a
 * generator needs `node:fs`, which this workspace's application tsconfig deliberately
 * cannot see, and a generator that runs when somebody remembers to run it is a
 * documentation process rather than a gate. A pure renderer plus a refusing test cannot
 * drift — the document is byte-identical to `renderMarkedBlock()` or CI is red, and the
 * failure message is the exact text to paste.
 *
 * ── WHY THIS IS NOT IN THE SHIPPED CLOSURE ───────────────────────────────────────
 *
 * Nothing in `src/` imports this module; only `tests/unit/design/glossary.test.ts` does.
 * `glossary.ts` is statically reachable from the evidentiary shell and pays for its
 * sentences once; the Markdown tables around them are a build-time artefact and would be
 * a second copy of the same prose in the entry chunk. `budgets.json` caps that closure at
 * 225 280 gzip bytes with `required: true`, and this is the cheapest kind of byte to not
 * spend.
 */

import {
  GLOSSED_TERMS,
  PRODUCT_WORDS,
  SQLSTATE_GLOSSES,
} from './glossary';

/** The marker pairs `glossary.test.ts` looks for in the Markdown. */
export const GENERATED_BLOCKS = ['product-words', 'glossed-terms', 'sqlstates'] as const;

export type GeneratedBlock = (typeof GENERATED_BLOCKS)[number];

export function openMarker(block: GeneratedBlock): string {
  return `<!-- GENERATED:${block} — rendered from src/design/glossary.ts. Do not edit by hand. -->`;
}

export function closeMarker(block: GeneratedBlock): string {
  return `<!-- /GENERATED:${block} -->`;
}

/** Escapes the two characters that would break a Markdown table cell. */
function cell(text: string): string {
  return text.replace(/\|/g, '\\|').replace(/\n/g, ' ');
}

function code(text: string): string {
  return `\`${text}\``;
}

/**
 * The nine product words: the word, its one sentence, and the exact thing it names.
 *
 * The third column is rendered as code because every value in it is an identifier a
 * reader is meant to go and look at — a table, a pair of tables, an endpoint path. The
 * one exception is the seed's own marker, which is not an identifier and is not dressed
 * as one.
 */
export function renderProductWords(): string {
  const rows = PRODUCT_WORDS.map(
    (entry) =>
      `| **${entry.key}** | ${cell(entry.sentence)} | ${entry.names.startsWith('the ') || entry.names.startsWith('a ') ? cell(entry.names) : code(entry.names)} |`,
  );
  return [
    '| Word | The one sentence | The exact thing it names |',
    '|---|---|---|',
    ...rows,
  ].join('\n');
}

/** The eighteen terms that are never replaced, with their first-use glosses. */
export function renderGlossedTerms(): string {
  const rows = GLOSSED_TERMS.map(
    (entry) => `| ${code(entry.label)} | ${cell(entry.gloss)} |`,
  );
  return ['| Term | First-use gloss |', '|---|---|', ...rows].join('\n');
}

/**
 * The SQLSTATE map.
 *
 * Rendered separately from the terms because these are not vocabulary the console chose —
 * they are codes the database prints, and the column heading says so.
 */
export function renderSqlstates(): string {
  const rows = SQLSTATE_GLOSSES.map((entry) => `| ${code(entry.code)} | ${cell(entry.gloss)} |`);
  return ['| Code the database printed | What it names |', '|---|---|', ...rows].join('\n');
}

export function renderBlock(block: GeneratedBlock): string {
  switch (block) {
    case 'product-words':
      return renderProductWords();
    case 'glossed-terms':
      return renderGlossedTerms();
    case 'sqlstates':
      return renderSqlstates();
  }
}

/** `openMarker … content … closeMarker`, exactly as it must appear in the document. */
export function renderMarkedBlock(block: GeneratedBlock): string {
  return `${openMarker(block)}\n\n${renderBlock(block)}\n\n${closeMarker(block)}`;
}

/**
 * What the document currently has between a block's markers.
 *
 * `null` means the markers are missing or out of order, which is a failure and not an
 * empty block: a generated table nobody can find is a table that stopped being checked.
 */
export function extractMarkedBlock(markdown: string, block: GeneratedBlock): string | null {
  const open = markdown.indexOf(openMarker(block));
  if (open < 0) return null;
  const contentStart = open + openMarker(block).length;
  const close = markdown.indexOf(closeMarker(block), contentStart);
  if (close < 0) return null;
  return markdown.slice(contentStart, close).trim();
}
