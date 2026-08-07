// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * SeverityBand — `mainline.virulence_class`, rendered.
 *
 * The band name is ALWAYS text, and there is no prop that removes it. Colour never
 * carries the band alone (`severity.ts`, the redundancy rule), because:
 *
 *   • the printed exhibit gets photocopied in monochrome;
 *   • a dichromat reads this ramp by lightness, which is monotone but compressed; and
 *   • a screenshot outlives the stylesheet that gave its colours meaning.
 *
 * The value is spelled the way the column spells it — `blood_fatal`, not "Critical".
 * A reader who sees the string on screen and greps the schema for it finds the same
 * string. That is what a verbatim surface is for, and softening it into a nicer word
 * would put a translation layer between an exhibit and the database it came from.
 *
 * `severity` is a SEPARATE, OPTIONAL fact. The band is derived from `max_severity` once,
 * in `clause_blame_closure`, by the database (ARCHITECTURE.md §5, finding S1, MI25).
 * This component never derives one from the other in either direction — it renders the
 * two numbers it was handed, side by side, each as itself.
 */

import { type ReactNode } from 'react';

import { bandFor, type VirulenceClass } from '../severity';
import a11y from './a11y.module.css';
import styles from './chips.module.css';

export interface SeverityBandProps {
  /** The value of `mainline.virulence_class`, verbatim. */
  readonly virulence: VirulenceClass;
  /**
   * `clause_blame_closure.max_severity`, 0–5, if the caller has it. Shown beside the
   * band, never used to compute it.
   */
  readonly severity?: number;
  readonly 'data-testid'?: string;
}

export function SeverityBand({
  virulence,
  severity,
  'data-testid': testId,
}: SeverityBandProps): ReactNode {
  const band = bandFor(virulence);
  return (
    <span
      className={`${styles.chip} ${styles.band}`}
      data-virulence={virulence}
      data-testid={testId}
    >
      <span className={a11y.visuallyHidden}>virulence class: {band.spoken}. </span>
      <span aria-hidden="true">{virulence}</span>
      {severity === undefined ? null : (
        <span className={styles.bandSeverity}>
          <span className={a11y.visuallyHidden}>max ancestral severity </span>
          <span aria-hidden="true">sev </span>
          {severity}
        </span>
      )}
    </span>
  );
}
