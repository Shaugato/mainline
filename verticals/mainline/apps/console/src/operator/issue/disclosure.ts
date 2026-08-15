// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * PROGRESSIVE DISCLOSURE OF DATA ALREADY IN HAND — and the sentence that makes it honest.
 *
 * R5. One press produces ONE real `POST /v1/demo/gate-run`, and that one response carries
 * all four beats. The screen reveals them in order under operator controls, because the
 * supervisor's own question — "but the counter says zero" — is what makes beat 3 legible.
 *
 * A judge with devtools open sees one request and three UI transitions. That LOOKS like
 * fakery unless the screen says what it is doing, so it says it, permanently, in the exact
 * shape the plan mandates:
 *
 *     one request · four beats · POST /v1/demo/gate-run · run_id <id> ·
 *     response received <ISO> · <n> bytes
 *
 * The line is not dismissible, not collapsible, and not behind a disclosure triangle. It
 * carries no close control at all — `renderDisclosureLine()` builds no button, and the
 * unit test asserts the element contains none. Revealing data you have received is not
 * fabrication; revealing it silently is indistinguishable from fabrication.
 *
 * **No timer schedules anything in this module, and nothing here measures time.** Reveals
 * happen on an operator's click and on nothing else. The only durations ever rendered are
 * the payload's own `elapsed_ms` per beat (`beats.ts`) and the real round-trip clock
 * (`pending.ts`), which is labelled as this browser's reading.
 */

import type { BeatView } from './beats';

// ───────────────────────────────────────────────────────────────────────────────────────
// The mandatory line
// ───────────────────────────────────────────────────────────────────────────────────────

/**
 * THIS MODULE DOES NOT COMPOSE THE SENTENCE. It renders one, permanently, and checks it.
 *
 * The kernel client composes it — `src/operator/kernel/gate-run.ts` `disclosureLine()` —
 * from the exchange and the payload it actually received, next to the request that produced
 * them. A second composer in a screen would be a second place for a mandated sentence to be
 * wrong, and the one thing worse than no disclosure line is two that disagree.
 *
 * What this module adds is the part a screen owes: the line is PERMANENT, and it is
 * CHECKED. `DISCLOSURE_SHAPE` is R5's shape:
 *
 *     one request · <n> beats · POST /v1/demo/gate-run · run_id <id> ·
 *     response received <ISO> · <n> bytes
 *
 * A sentence that does not match is still rendered **verbatim** — never replaced, never
 * hidden, because what the kernel composed is evidence — and the strip is marked
 * `data-shape="unexpected"` with a note saying so. A screen that quietly repaired a
 * malformed disclosure line would be disclosing something other than what happened.
 */
export const DISCLOSURE_SHAPE =
  /^one request · \d+ beats · POST \/v1\/demo\/gate-run · run_id .+ · response received .+ · \d+ bytes$/;

export function disclosureShapeIsExpected(sentence: string): boolean {
  return DISCLOSURE_SHAPE.test(sentence);
}

/**
 * The permanent strip. No close control, no `hidden`, no collapse, no `<details>`.
 *
 * The caveat beneath is a SIBLING element rather than part of the sentence, so the mandated
 * line keeps exactly the shape the plan specifies while the reader is still told whose
 * clock stamped the instant inside it.
 */
export function renderDisclosureLine(sentence: string): HTMLElement {
  const strip = document.createElement('div');
  strip.className = 'cow-disclosure';
  strip.dataset.permanent = 'true';
  const expected = disclosureShapeIsExpected(sentence);
  strip.dataset.shape = expected ? 'expected' : 'unexpected';

  const line = document.createElement('p');
  line.className = 'cow-disclosure__line';
  line.dataset.disclosure = 'line';
  line.textContent = sentence;
  strip.append(line);

  const caveat = document.createElement('p');
  caveat.className = 'cow-disclosure__caveat';
  caveat.textContent =
    'Every beat below came back in that one response. Each is revealed on a click, and each ' +
    'shows the duration the server measured for it. The received-at instant above is this ' +
    'browser’s clock.';
  strip.append(caveat);

  if (!expected) {
    const warning = document.createElement('p');
    warning.className = 'cow-disclosure__caveat';
    warning.dataset.disclosure = 'shape-warning';
    warning.textContent =
      'This line is shown exactly as the transport composed it, and it does not have the ' +
      'shape this screen expected. Nothing has been substituted or repaired.';
    strip.append(warning);
  }

  return strip;
}

// ───────────────────────────────────────────────────────────────────────────────────────
// The reveal, under operator control
// ───────────────────────────────────────────────────────────────────────────────────────

export interface Disclosure {
  /** How many beats are on screen, counted from the first. */
  readonly revealed: number;
  readonly total: number;
  readonly canAdvance: boolean;
  /** Reveals exactly one more beat. Returns the new count. Never skips, never rewinds. */
  advance(): number;
  /** Reveals everything at once — the affordance for a reader who does not want the story. */
  revealAll(): number;
  subscribe(listener: (revealed: number) => void): () => void;
}

/**
 * `initial` is how much a press shows immediately: the read and the first refusal. Beats 3
 * and 4 wait for the operator's question. There is no timer behind either of them.
 */
export function createDisclosure(total: number, initial: number): Disclosure {
  const cap = Math.max(0, total);
  let revealed = Math.min(Math.max(0, initial), cap);
  const listeners = new Set<(revealed: number) => void>();

  const announce = (): number => {
    for (const listener of listeners) listener(revealed);
    return revealed;
  };

  return {
    get revealed(): number {
      return revealed;
    },
    get total(): number {
      return cap;
    },
    get canAdvance(): boolean {
      return revealed < cap;
    },
    advance(): number {
      if (revealed >= cap) return revealed;
      revealed += 1;
      return announce();
    },
    revealAll(): number {
      if (revealed >= cap) return revealed;
      revealed = cap;
      return announce();
    },
    subscribe(listener): () => void {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

/**
 * The label on the control that reveals the NEXT beat.
 *
 * Every number in a label is taken from the beat it is about, so the control cannot
 * promise something the payload does not then show. When the next beat is the one that
 * forced the projected counter, the label quotes the value it was forced to. When it is
 * the admission, the label names the act — no number, because none is claimed yet.
 */
export function advanceLabel(next: BeatView | undefined): string | null {
  if (next === undefined) return null;
  const forcedTo = next.observed.counter_forced_to;
  if (forcedTo !== undefined && forcedTo !== null) {
    return `But the counter now reads ${forcedTo} ▸`;
  }
  if (next.isAdmission) return 'Answer the obligation, then issue again ▸';
  return `Show beat ${next.ordinal} ▸`;
}
