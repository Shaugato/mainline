// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE ANNOUNCER — how a refusal reaches an operator who cannot see the screen.
 *
 * Two live regions per document, created once, never removed: a `role="status"` for
 * polite messages and a `role="alert"` for assertive ones. Both are visually hidden and
 * both are real text, because a live region built out of a CSS pseudo-element announces
 * nothing.
 *
 * ── THE ONE RULE THAT IS NOT ERGONOMICS ──────────────────────────────────────────
 *
 * `announceVerbatim()` announces the EXACT string it is given, and refuses to be given a
 * string it would have to alter. It throws on leading or trailing whitespace, on an
 * embedded newline, and on the empty string.
 *
 * That is not fussiness. D18 and ui.md §1.1: a constraint name, a SQLSTATE and a digest
 * are what the database emitted, and *a prettified refusal is a different refusal*. The
 * eye gets `gate_closed_when_issued` in the mono face; speech output must get the same
 * twenty-three characters, not "gate closed when issued" and not "Gate closed (when
 * issued)". A helper that trimmed, title-cased or re-spaced on the way through would be
 * a paraphrase performed by the accessibility layer — the one place nobody would look
 * for it.
 *
 * Prose ABOUT a verbatim value is fine and expected: `announce()` takes any string, and
 * the intended call is `announce('Merge refused by constraint:'); announceVerbatim(name)`.
 * The split is the point. One function may compose; the other may not.
 */

const POLITE_ID = 'mainline-live-polite';
const ASSERTIVE_ID = 'mainline-live-assertive';

/**
 * The visually-hidden recipe, inline.
 *
 * Inline rather than a CSS module because this element is created imperatively, often
 * before any surface stylesheet has loaded, and a live region that is briefly visible is
 * a live region that briefly rearranges the page. `clip-path` plus a 1px box is the
 * form that keeps the text in the accessibility tree; `display: none` and
 * `visibility: hidden` both remove it, which is the classic way an announcer ships
 * announcing nothing.
 */
const VISUALLY_HIDDEN =
  'position:absolute;width:1px;height:1px;margin:-1px;padding:0;overflow:hidden;' +
  'clip-path:inset(50%);white-space:nowrap;border:0;';

export type Politeness = 'polite' | 'assertive';

export interface Announcer {
  /** Announces prose the console composed. */
  readonly announce: (message: string, politeness?: Politeness) => void;
  /**
   * Announces a string the DATABASE emitted, unchanged.
   * Throws if the string would have to be altered to be announced.
   */
  readonly announceVerbatim: (value: string, politeness?: Politeness) => void;
  /** The current contents of a region. Exported so tests assert what was said. */
  readonly read: (politeness: Politeness) => string;
  /** Empties both regions without removing them. */
  readonly clear: () => void;
  /** Removes the regions. Used by tests; production never calls it. */
  readonly destroy: () => void;
}

function ensureRegion(doc: Document, id: string, politeness: Politeness): HTMLElement {
  const existing = doc.getElementById(id);
  if (existing !== null) return existing;

  const region = doc.createElement('div');
  region.id = id;
  region.setAttribute('role', politeness === 'assertive' ? 'alert' : 'status');
  region.setAttribute('aria-live', politeness);
  // `aria-atomic="true"` makes the whole region re-read on every change. Without it a
  // screen reader may announce only the diff, which for a constraint name that shares a
  // prefix with the previous one produces a fragment nobody can act on.
  region.setAttribute('aria-atomic', 'true');
  region.setAttribute('data-testid', id);
  region.setAttribute('style', VISUALLY_HIDDEN);
  doc.body.appendChild(region);
  return region;
}

/** Everything `announceVerbatim` refuses, with the reason, or `null` when the value is legal. */
export function verbatimRefusal(value: string): string | null {
  if (value === '') {
    return 'the empty string. An announcer that accepts "" reports success and says nothing.';
  }
  if (value !== value.trim()) {
    return (
      `"${value}" has leading or trailing whitespace. Trimming it here would make speech output ` +
      'and the mono face disagree about what the database emitted.'
    );
  }
  if (/[\n\r]/.test(value)) {
    return (
      'a multi-line value. A live region flattens newlines, so the announced string would differ ' +
      'from the rendered one. Announce each line, or announce a description and render the block.'
    );
  }
  return null;
}

/**
 * The document's announcer. Idempotent: calling it twice returns handles onto the same
 * two regions, because two `role="alert"` regions produce two announcements of every
 * refusal.
 */
export function createAnnouncer(doc: Document): Announcer {
  const regionFor = (politeness: Politeness): HTMLElement =>
    politeness === 'assertive'
      ? ensureRegion(doc, ASSERTIVE_ID, 'assertive')
      : ensureRegion(doc, POLITE_ID, 'polite');

  const write = (politeness: Politeness, text: string): void => {
    const region = regionFor(politeness);
    // Clearing first makes a repeated identical message announce again. A refusal
    // repeated because the operator retried is a refusal that must be heard twice.
    region.textContent = '';
    region.textContent = text;
  };

  return {
    announce: (message: string, politeness: Politeness = 'polite'): void => {
      write(politeness, message);
    },
    announceVerbatim: (value: string, politeness: Politeness = 'assertive'): void => {
      const refusal = verbatimRefusal(value);
      if (refusal !== null) {
        throw new Error(
          `a11y/announce: announceVerbatim() refuses ${refusal} ` +
            'A verbatim value is announced exactly as the database emitted it, or not at all ' +
            '(docs/leads/ui.md D18).',
        );
      }
      write(politeness, value);
    },
    read: (politeness: Politeness): string => regionFor(politeness).textContent ?? '',
    clear: (): void => {
      write('polite', '');
      write('assertive', '');
    },
    destroy: (): void => {
      doc.getElementById(POLITE_ID)?.remove();
      doc.getElementById(ASSERTIVE_ID)?.remove();
    },
  };
}
