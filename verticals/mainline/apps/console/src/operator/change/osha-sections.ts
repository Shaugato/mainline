// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE OSHA FIVE — 29 CFR 1910.119(l)(2), used as the body of the form.
 *
 * `(l)(1)` requires written procedures to manage changes *"to process chemicals,
 * technology, equipment, and procedures"* other than replacements in kind. `(l)(2)`
 * requires those procedures to address five things **prior to any change**. Those five
 * are the form, and a management-of-change screen that carries them is legible on sight
 * to anyone who has worked under Process Safety Management. They are printed here in the
 * regulation's own words, cited to the regulation, and never presented as this product's
 * own text (operator-systems-plan R13).
 *
 * ── R12 — THE RULING THIS MODULE EXISTS TO ENFORCE ───────────────────────────────────
 *
 * **No proposed clause text exists anywhere in this deployment.**
 * `mainline.change_request` (`0051_change_request.sql:59-102`) has no title, no
 * description, no proposed text, no requester and no target-clause column. A diff screen
 * showing "old" against "new" would therefore have a real left side and a FABRICATED
 * right side, and the console's existing `features/diff/` — which a builder will reach
 * for — is out of bounds for exactly that reason.
 *
 * So:
 *   • the left side is one REAL string: the clause version this deployment returned,
 *     verbatim, `SYNTHETIC —` prefix and all;
 *   • the right side is one TYPED string, entered into the box on camera, read from the
 *     live `value` of a `<textarea>` at the moment the diff is asked for;
 *   • the diff is computed in the browser, by `diffTokens` below, and is labelled as
 *     exactly that;
 *   • before anything is typed, NO diff renders at all. There is no seeded value, no
 *     placeholder that reads as content, no `defaultValue`, and no code path in this file
 *     that can put a character into that box.
 *
 * A grep for a clause-shaped string in this directory finds nothing, and
 * `tests/unit/operator/change/screen.test.ts` proves the stronger statement: every word
 * on the right of the diff is a word that was typed.
 *
 * ── SECTION (iv) ─────────────────────────────────────────────────────────────────────
 *
 * *"Necessary time period for the change"* has no column either. It renders as an
 * absence, and the screen points instead at the one bounded duration this deployment
 * genuinely carries — the `max_ttl_hours` ceiling on the lattice's emergency route, which
 * is real, live, and answers the IChemE Safety Centre's own named failure mode.
 */

import { el, txt } from './ribbon';

export interface OshaHeading {
  /** The paragraph of 29 CFR 1910.119 this heading is, cited on screen. */
  readonly cite: string;
  /** The regulation's own words. */
  readonly heading: string;
}

/** 29 CFR 1910.119(l)(2)(i)–(v), verbatim and in order. */
export const OSHA_HEADINGS: readonly OshaHeading[] = [
  { cite: '1910.119(l)(2)(i)', heading: 'The technical basis for the proposed change' },
  { cite: '1910.119(l)(2)(ii)', heading: 'Impact of change on safety and health' },
  { cite: '1910.119(l)(2)(iii)', heading: 'Modifications to operating procedures' },
  { cite: '1910.119(l)(2)(iv)', heading: 'Necessary time period for the change' },
  {
    cite: '1910.119(l)(2)(v)',
    heading: 'Authorization requirements for the proposed change',
  },
];

/** Wrap a body in one of the five headings. Index is 0-based into `OSHA_HEADINGS`. */
export function renderOshaSection(index: number, body: HTMLElement): HTMLElement {
  const heading = OSHA_HEADINGS[index];
  if (heading === undefined) {
    throw new RangeError(`no OSHA heading at index ${String(index)}`);
  }

  const section = el('section', 'moc-section');
  const head = el('div', 'moc-section-head');
  head.append(el('span', 'moc-section-index', `${String(index + 1)}.`));
  const title = el('h2', 'moc-section-heading', heading.heading);
  title.id = `moc-osha-${String(index)}`;
  head.append(title);
  head.append(el('span', 'moc-section-cite', heading.cite));
  section.append(head);

  section.setAttribute('aria-labelledby', title.id);
  const bodyWrap = el('div', 'moc-section-body', body);
  section.append(bodyWrap);
  return section;
}

/* ── typed fields ─────────────────────────────────────────────────────────────────── */

export interface TypedFieldOptions {
  readonly id: string;
  readonly label: string;
  readonly placeholder: string;
  readonly rows: number;
  /** The sentence that keeps this field out of the data register. Mandatory. */
  readonly note: string;
}

/**
 * A field a human types into on camera.
 *
 * It has a caret, a placeholder, and a note saying no column carries it. It is never
 * given a value by this module, never echoed back as server data, and never given a
 * provenance chip. `placeholder` is styled as placeholder text and is not content: it
 * disappears the instant a key is pressed, which is what stops a still frame from
 * reading it as a stored value.
 */
export function renderTypedField(options: TypedFieldOptions): {
  readonly root: HTMLElement;
  readonly field: HTMLTextAreaElement;
} {
  const root = el('div');
  const label = el('label', 'moc-label', options.label);
  label.htmlFor = options.id;
  root.append(label);

  const field = el('textarea', 'moc-typed-field');
  field.id = options.id;
  field.rows = options.rows;
  field.placeholder = options.placeholder;
  // Deliberately not set: value, defaultValue, textContent. There is no code path in this
  // directory that writes a character into an operator field.
  root.append(field);
  root.append(txt(options.note, 'moc-typed-note'));
  return { root, field };
}

/* ── the diff ─────────────────────────────────────────────────────────────────────── */

export type DiffOp = 'same' | 'del' | 'ins';

export interface DiffToken {
  readonly op: DiffOp;
  readonly text: string;
}

/** Split into words and the whitespace between them, losslessly. */
function tokenise(value: string): readonly string[] {
  return value.split(/(\s+)/).filter((token) => token !== '');
}

/**
 * A word-level diff, computed here, in this browser, over two strings.
 *
 * Longest-common-subsequence over tokens. Both inputs are short — one clause and one
 * sentence a human just typed — so the quadratic table is a few thousand cells and there
 * is no reason to reach for anything cleverer or to import one.
 *
 * This is the ONLY comparison on the screen. It is not a re-derivation, it is not a
 * kernel claim, and the label beside it says so.
 */
export function diffTokens(left: string, right: string): readonly DiffToken[] {
  const a = tokenise(left);
  const b = tokenise(right);

  // lcs[i][j] = length of the longest common subsequence of a[i:] and b[j:]
  const lcs: number[][] = Array.from({ length: a.length + 1 }, () =>
    new Array<number>(b.length + 1).fill(0),
  );
  for (let i = a.length - 1; i >= 0; i -= 1) {
    for (let j = b.length - 1; j >= 0; j -= 1) {
      const row = lcs[i];
      const next = lcs[i + 1];
      if (row === undefined || next === undefined) continue;
      row[j] = a[i] === b[j] ? (next[j + 1] ?? 0) + 1 : Math.max(next[j] ?? 0, row[j + 1] ?? 0);
    }
  }

  const out: DiffToken[] = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    const left1 = a[i];
    const right1 = b[j];
    if (left1 === right1 && left1 !== undefined) {
      out.push({ op: 'same', text: left1 });
      i += 1;
      j += 1;
      continue;
    }
    const down = lcs[i + 1]?.[j] ?? 0;
    const across = lcs[i]?.[j + 1] ?? 0;
    if (down >= across) {
      out.push({ op: 'del', text: left1 ?? '' });
      i += 1;
    } else {
      out.push({ op: 'ins', text: right1 ?? '' });
      j += 1;
    }
  }
  while (i < a.length) {
    out.push({ op: 'del', text: a[i] ?? '' });
    i += 1;
  }
  while (j < b.length) {
    out.push({ op: 'ins', text: b[j] ?? '' });
    j += 1;
  }
  return out;
}

const DIFF_CLASS: Readonly<Record<DiffOp, string>> = {
  same: '',
  del: 'moc-diff-del',
  ins: 'moc-diff-ins',
};

/** Render the tokens. Whitespace tokens keep their op so the reconstruction is exact. */
export function renderDiff(tokens: readonly DiffToken[]): HTMLElement {
  const box = el('div', 'moc-diff');
  box.setAttribute('role', 'group');
  box.setAttribute('aria-label', 'word-level comparison computed in this browser');
  for (const token of tokens) {
    box.append(el('span', DIFF_CLASS[token.op], token.text));
  }
  return box;
}

/* ── section (iii): modifications to operating procedures ─────────────────────────── */

/** The clause version as `GET /v1/clauses/{uuid}/versions/{commit}` returned it. */
export interface ClauseOfRecord {
  readonly canonText: string;
  readonly printedLabel: string | null;
  readonly commitId: string | null;
  readonly anchors: readonly string[];
  /** The verbatim request line this clause arrived on. */
  readonly readFrom: string;
  /**
   * Why this clause is on this screen. `mainline.change_request` has NO target-clause
   * column, so the screen must never say "the clause this change request targets".
   * Required, and printed under the quote.
   */
  readonly relationNote: string;
}

export interface ModificationsSection {
  readonly root: HTMLElement;
  readonly proposed: HTMLTextAreaElement;
}

/**
 * The clause of record, the box the engineer types into, and the diff between them.
 *
 * The compare control reads `proposed.value` at press time. If it is empty, no diff is
 * rendered and the screen says why — an empty right side is an empty right side, not an
 * invitation to fill it from somewhere.
 */
export function renderModificationsSection(clause: ClauseOfRecord | null): ModificationsSection {
  const root = el('div');

  if (clause === null) {
    root.append(
      el(
        'p',
        'moc-absent',
        'The clause of record was not returned by this page load, so no text is quoted and ' +
          'no comparison is offered. There is no stored copy of it in this page.',
      ),
    );
  } else {
    const label = el('span', 'moc-label', 'Clause of record — current text, as returned');
    root.append(label);

    const quote = el('blockquote', 'moc-quote', clause.canonText);
    root.append(quote);

    const meta = el('p', 'moc-provenance');
    meta.append(document.createTextNode('Printed label '));
    meta.append(
      clause.printedLabel === null
        ? el('span', 'moc-absent-inline', 'not read')
        : el('code', 'moc-db', clause.printedLabel),
    );
    if (clause.commitId !== null) {
      meta.append(document.createTextNode(' at commit '));
      meta.append(el('code', 'moc-db', clause.commitId));
    }
    if (clause.anchors.length > 0) {
      meta.append(document.createTextNode(' · anchors '));
      meta.append(el('code', 'moc-db', clause.anchors.join(', ')));
    }
    root.append(meta);
    root.append(txt(clause.relationNote));
    root.append(txt(clause.readFrom, 'moc-exchange'));
  }

  const typed = renderTypedField({
    id: 'moc-proposed-text',
    label: 'Proposed wording',
    placeholder: 'type the proposed wording',
    rows: 4,
    note:
      'Typed here, now. This deployment carries no proposed text: mainline.change_request ' +
      'has no column for it, so there is nothing to load into this box and nothing was.',
  });
  root.append(typed.root);

  const compare = el('button', 'moc-compare', 'Compare with clause of record');
  compare.type = 'button';
  root.append(compare);

  const output = el('div');
  output.setAttribute('aria-live', 'polite');
  root.append(output);

  compare.addEventListener('click', () => {
    output.replaceChildren();
    const proposedText = typed.field.value;
    if (clause === null) {
      output.append(
        el('p', 'moc-absent', 'No clause of record was returned, so there is nothing to compare.'),
      );
      return;
    }
    if (proposedText.trim() === '') {
      output.append(
        el(
          'p',
          'moc-absent',
          'Nothing has been typed, so there is nothing to compare. The right-hand side of ' +
            'this comparison has exactly one possible source and it is the box above.',
        ),
      );
      return;
    }
    output.append(renderDiff(diffTokens(clause.canonText, proposedText)));
    output.append(
      txt(
        'Computed in this browser, just now, between the clause text this deployment ' +
          'returned (struck through) and the wording typed into the box above ' +
          '(underlined). It is not a stored diff, it is not a kernel claim, and no part of ' +
          'the right-hand side came from the database.',
      ),
    );
  });

  return { root, proposed: typed.field };
}
