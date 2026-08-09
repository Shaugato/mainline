// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The tokeniser the clause diff is drawn against.
 *
 * Three properties, and every one of them is asserted in `tests/unit/diff/engine.test.ts`:
 *
 *   1. TOTAL — concatenating the tokens reproduces the input string exactly. There is no
 *      character class this function drops, normalises or folds. A tokeniser that
 *      swallowed a non-breaking space would produce a diff that reassembles into a
 *      DIFFERENT clause than the one in the column, and the screen would still look fine.
 *   2. CONTIGUOUS — token `n+1` starts where token `n` ended, from 0 to `text.length`.
 *      Offsets are into `canon_text` and nothing else (`contracts/clause.schema.json`).
 *   3. PURE — no locale, no `Intl.Segmenter`, no case folding. `Intl.Segmenter` is
 *      tempting and is the wrong tool here: its output depends on the ICU version the
 *      browser shipped, so the same payload would diff differently on two machines and
 *      the cinema screenshots (D12) would stop being reproducible.
 *
 * Three classes, because a clause is prose with identifiers in it:
 *
 *   `word`  — a run of letters, digits and marks, plus the joiners that hold an
 *             identifier or a quantity together: `HPU-0412`, `zero-energy-verification`,
 *             `4024.1`, `officer’s`.
 *   `space` — a run of whitespace, kept as its own token so that a whitespace-only edit
 *             is visible rather than absorbed into a neighbour.
 *   `punct` — anything else, ONE CHARACTER AT A TIME, so that `unit.` → `unit;` is a
 *             one-character change rather than a whole-word replacement.
 *
 * The joiner set is deliberately small. Hyphen, underscore, slash, full stop and
 * apostrophe are in it because plant tags, standards citations, setpoints and possessives
 * use them. A comma is not: a comma between two clauses of a sentence is punctuation, and
 * treating it as part of the preceding word makes every list edit look larger than it is.
 */

import type { Token, TokenKind } from '../model';

/**
 * Whitespace, as CODE POINTS rather than as literal characters or as `\s`.
 *
 * Two reasons, both practical. `\s`'s membership is defined by the ECMAScript edition
 * the engine implements, and a set that can change under us is a set the offsets cannot
 * be trusted against. Literal characters in a source file survive one careless
 * find-and-replace and no more — U+00A0 and U+0020 are indistinguishable on screen, and
 * this is the one file where confusing them silently changes a diff.
 */
const SPACE_CODE_POINTS: readonly number[] = [
  0x0009, // character tabulation
  0x000a, // line feed
  0x000b, // line tabulation
  0x000c, // form feed
  0x000d, // carriage return
  0x0020, // space
  0x0085, // next line
  0x00a0, // no-break space
  0x1680, // ogham space mark
  0x2000, // en quad
  0x2001, // em quad
  0x2002, // en space
  0x2003, // em space
  0x2004, // three-per-em space
  0x2005, // four-per-em space
  0x2006, // six-per-em space
  0x2007, // figure space
  0x2008, // punctuation space
  0x2009, // thin space
  0x200a, // hair space
  0x2028, // line separator
  0x2029, // paragraph separator
  0x202f, // narrow no-break space
  0x205f, // medium mathematical space
  0x3000, // ideographic space
  0xfeff, // zero-width no-break space
];

const SPACE = new Set(SPACE_CODE_POINTS.map((point) => String.fromCodePoint(point)));

/**
 * Characters that hold an identifier, a citation or a quantity together, as code points
 * for the same reason: U+002D and U+2011 are one pixel apart and one of them appears in
 * every plant tag this product will ever see.
 */
const JOINER_CODE_POINTS: readonly number[] = [
  0x002d, // hyphen-minus
  0x2011, // non-breaking hyphen
  0x005f, // low line
  0x002f, // solidus
  0x002e, // full stop
  0x0027, // apostrophe
  0x2019, // right single quotation mark, used as an apostrophe
];

const JOINERS = new Set(JOINER_CODE_POINTS.map((point) => String.fromCodePoint(point)));

const ALNUM = /[\p{L}\p{N}\p{M}]/u;

function classify(char: string): TokenKind {
  if (SPACE.has(char)) return 'space';
  if (ALNUM.test(char)) return 'word';
  return 'punct';
}

/**
 * A joiner is part of a word only when it sits BETWEEN two alphanumerics.
 *
 * `HPU-0412` is one word; `isolated, and` is `isolated` `,` ` ` `and`; and a full stop
 * ending a sentence stays its own token, which is what makes `unit.` → `unit;` read as
 * the one-character edit it is.
 */
function joinsWord(text: string, index: number): boolean {
  const char = text[index];
  if (char === undefined || !JOINERS.has(char)) return false;
  const before = text[index - 1];
  const after = text[index + 1];
  if (before === undefined || after === undefined) return false;
  return ALNUM.test(before) && ALNUM.test(after);
}

/**
 * Splits `text` into contiguous tokens.
 *
 * Iteration is over UTF-16 code units rather than code points, deliberately, and by the
 * same convention every `canon_text` offset in this console uses: a JavaScript string
 * index, a `String.prototype.slice` argument and the number reported here are all the
 * same number. Iterating code points would produce offsets no `slice` in the codebase
 * could consume, which is a subtler defect than an astral character landing in a token
 * of its own.
 */
export function tokenise(text: string): readonly Token[] {
  const tokens: Token[] = [];
  const length = text.length;
  let index = 0;

  while (index < length) {
    const start = index;
    const head = text.charAt(index);
    const kind = classify(head);

    if (kind === 'punct' && !joinsWord(text, index)) {
      index += 1;
      tokens.push({ text: text.slice(start, index), start, end: index, kind: 'punct' });
      continue;
    }

    if (kind === 'space') {
      while (index < length && classify(text.charAt(index)) === 'space') index += 1;
      tokens.push({ text: text.slice(start, index), start, end: index, kind: 'space' });
      continue;
    }

    // A word: alphanumerics, plus any joiner sitting between two of them.
    while (index < length) {
      const char = text.charAt(index);
      if (ALNUM.test(char) || joinsWord(text, index)) {
        index += 1;
        continue;
      }
      break;
    }
    tokens.push({ text: text.slice(start, index), start, end: index, kind: 'word' });
  }

  return tokens;
}
