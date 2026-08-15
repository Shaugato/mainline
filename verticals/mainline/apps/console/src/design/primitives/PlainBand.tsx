// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * PlainBand — the three sentences a site supervisor reads before the screen starts.
 *
 * Ruling R6, in one sentence: *every screen opens with three sentences a site supervisor
 * can read, and every exact thing that was already on it is one deliberate, permanent
 * click away.* This is the band. It sits ABOVE the surface and is not a summary of it —
 * nothing below moves away, and four of the things below never even collapse.
 *
 * ── WHY THE CEILING IS THREE, AND WHY IT IS ENFORCED ─────────────────────────────
 *
 * A band that may grow is a band that grows, and a fourth sentence is read by nobody
 * while pushing the refusal further down the page. Three is the number R6 sets and this
 * component refuses a fourth rather than trusting a reviewer to count. The refusal is a
 * throw, in the idiom `resources.ts` and `registers.ts` already use: caught by
 * `app/ErrorBoundary.tsx`, impossible to miss in the test that renders the screen, and not
 * negotiable by the person adding the sentence.
 *
 * ── THE SYNTHETIC SLOT (R5) ──────────────────────────────────────────────────────
 *
 * `demo_world.sql` says in its own bytes that every row it seeds corresponds to nobody,
 * that free text opens with `SYNTHETIC —`, and that every JSONB payload carries
 * `"synthetic": true`. R5 makes that a rule for the console's prose too: **any narrative
 * sentence sourced from the demo seed sits under a persistent SYNTHETIC marker.**
 *
 * The marker is a SLOT rather than a boolean, for one reason. The console must not be able
 * to produce the marker on its own — whoever fills this slot is the surface that read the
 * seed's own `SYNTHETIC —` prefix, and rendering that verbatim is R5's requirement. A
 * `synthetic` prop would let a screen assert synthetic-ness it never observed, and the
 * inverse mistake — a screen forgetting the prop — would silently drop the disclosure.
 *
 * The slot sits in the HEAD, above the sentences, because a marker a reader meets after
 * the narrative arrives too late to change how the narrative was read.
 *
 * ── WHAT A SENTENCE MAY SAY ──────────────────────────────────────────────────────
 *
 * R7's test, unchanged: *can I point at the field it came from?* If not, delete it. The
 * twelve forbidden words are in `glossary.ts` as `FORBIDDEN_WORDS`, and
 * `forbiddenWordsIn()` is available to any test that wants to hold a deck of sentences to
 * them.
 */

import { type ReactNode } from 'react';

import styles from './plain.module.css';

/** R6's ceiling. Three sentences, and the fourth is a refusal rather than a scroll. */
export const MAX_SENTENCES = 3;

export interface PlainBandProps {
  /**
   * Two or three words, lower case — what this screen is. Rendered in the label style.
   * Optional: a band with no kicker is a band that gets straight to the sentence.
   */
  readonly kicker?: string;
  /**
   * At most three sentences, in reading order. The first is the one a reader who reads
   * nothing else will read, and it keeps the primary ink; the rest support it.
   */
  readonly sentences: readonly string[];
  /**
   * The SYNTHETIC marker (R5), or any other persistent marker this screen must carry
   * beside its opening. Rendered in the head, above the sentences.
   */
  readonly marker?: ReactNode;
  /**
   * Anything that belongs with the band rather than with the surface — a `Disclosure`
   * naming what the reader will find below, a link built with `hrefWithDetail()`.
   */
  readonly children?: ReactNode;
  readonly className?: string;
  readonly 'data-testid'?: string;
}

export function PlainBand({
  kicker,
  sentences,
  marker,
  children,
  className,
  'data-testid': testId,
}: PlainBandProps): ReactNode {
  if (sentences.length === 0) {
    throw new Error(
      'PlainBand: no sentences. A band with nothing in it is a box a reader learns to skip, ' +
        'and the screen below then opens at its own reading level with no on-ramp at all ' +
        '(docs/leads/two-audience-ux-plan.md R6).',
    );
  }
  if (sentences.length > MAX_SENTENCES) {
    throw new Error(
      `PlainBand: ${sentences.length} sentences, and R6 sets the ceiling at ${MAX_SENTENCES}. A ` +
        'fourth sentence is read by nobody and pushes the refusal further down the page. Move ' +
        'the material into a Disclosure that names what is inside it.',
    );
  }
  const blank = sentences.filter((sentence) => sentence.trim() === '');
  if (blank.length > 0) {
    throw new Error(
      'PlainBand: an empty sentence. A blank line in the on-ramp reads as a sentence that ' +
        'failed to load, which is the console reporting a fault it does not have.',
    );
  }

  return (
    <div
      className={className === undefined ? styles.band : `${styles.band} ${className}`}
      data-plain-band=""
      data-testid={testId}
    >
      {kicker === undefined && marker === undefined ? null : (
        <div className={styles.bandHead}>
          {kicker === undefined ? null : <span className={styles.bandKicker}>{kicker}</span>}
          {marker === undefined ? null : <span className={styles.bandMarker}>{marker}</span>}
        </div>
      )}
      <div className={styles.bandSentences}>
        {sentences.map((sentence) => (
          <p key={sentence} className={styles.bandSentence}>
            {sentence}
          </p>
        ))}
      </div>
      {children}
    </div>
  );
}
