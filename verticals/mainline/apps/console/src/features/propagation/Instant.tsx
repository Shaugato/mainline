// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * An instant, and the interval between it and a NAMED reference instant.
 *
 * Three rules, all of them about not nagging and not lying:
 *
 *   1. The timestamp is rendered VERBATIM, in the mono face, exactly as the column
 *      emitted it. No "3 weeks ago", no locale reformatting, no timezone guessing. The
 *      read API renders every TIMESTAMPTZ in UTC and that string is the evidence.
 *   2. The interval names what it was measured against. "231 days past due" is a claim
 *      about a clock; "231 days past due, measured against observed_at 2026-08-07T…" is
 *      a fact a reader can check. The reference is never the reader's own clock.
 *   3. `past_due` gets emphasis weight and the refusal accent — and nothing else. No
 *      pulse, no badge, no exclamation mark, no colour fill. The SLA clock is a fact,
 *      never a nag: a console that nags is a console people learn to dismiss, and this
 *      one has to still be legible on the day it matters.
 */

import { type ReactNode } from 'react';

import { Mono } from '../../design/primitives';

import { wholeDays, type Interval, type SlaStanding } from './model';
import styles from './propagation.module.css';

export interface InstantProps {
  /** What the instant is: `due_by`, `opened_at`, `declination_expires_at`. */
  readonly label: string;
  /** The instant, verbatim. `null` renders as an explicit absence. */
  readonly value: string | null;
  /** The measured interval, or `null` when no interval is meaningful for this field. */
  readonly interval: Interval | null;
  /**
   * Sets `data-standing`, which is the only styling hook. Omit for instants that carry
   * no SLA meaning — an `opened_at` is not late, it is just old.
   */
  readonly standing?: SlaStanding;
  readonly 'data-testid'?: string;
}

/**
 * The sentence for an interval, in the payload's own terms.
 *
 * `deltaMs` is `reference − subject`, so a positive value means the subject instant is in
 * the past. The wording says which side of the reference it fell on and never editorialises
 * about whose fault that is.
 */
function phrase(interval: Interval): string {
  const days = wholeDays(interval.deltaMs);
  if (days > 0) return `${days} day(s) before the reference instant`;
  if (days < 0) return `${Math.abs(days)} day(s) after the reference instant`;
  return 'within a day of the reference instant';
}

export function Instant({
  label,
  value,
  interval,
  standing,
  'data-testid': testId,
}: InstantProps): ReactNode {
  return (
    <span className={styles.clock} data-testid={testId} data-standing={standing}>
      <span className={styles.clockReference}>{label}</span>
      {value === null ? (
        <span className={styles.absent} data-absent="true">
          not set
        </span>
      ) : (
        <span className={styles.clockValue} data-standing={standing}>
          <Mono>{value}</Mono>
        </span>
      )}
      {interval?.measurable !== true ? null : (
        <span className={styles.clockReference}>
          {phrase(interval)} — reference <Mono>{interval.reference}</Mono>
        </span>
      )}
    </span>
  );
}
