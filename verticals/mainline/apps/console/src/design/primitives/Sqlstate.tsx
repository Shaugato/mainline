// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Sqlstate — the five characters that say which kind of refusal this was.
 *
 * `spec/errors.md` makes the code set CLOSED over the gate path. This component knows
 * that taxonomy (via `../sqlstate`) and says, loudly, when a code falls outside it —
 * because a code outside the set means the database refused for a reason nobody
 * modelled, which is a defect report rather than an ordinary refusal.
 *
 * It does NOT translate the code into prose. The expectation class is a fact about the
 * code; the human meaning is a fact about the refusal payload, and D18 says the payload
 * carries its own words.
 */

import { CLASS_LABEL, sqlstateClass } from '../sqlstate';
import a11y from './a11y.module.css';
import styles from './verbatim.module.css';

import { type ReactNode } from 'react';

export interface SqlstateProps {
  /** The SQLSTATE exactly as reported. Five characters; not normalised, not padded. */
  readonly code: string;
  /**
   * Show the expectation class beside the code. Off by default — on the refusal bar the
   * code is the point and the class is context the reader can ask for. A code outside
   * the taxonomy overrides this and is always announced.
   */
  readonly showClass?: boolean;
  readonly tone?: 'neutral' | 'refuse';
  readonly 'data-testid'?: string;
}

export function Sqlstate({
  code,
  showClass = false,
  tone = 'neutral',
  'data-testid': testId,
}: SqlstateProps): ReactNode {
  const klass = sqlstateClass(code);
  return (
    <span className={styles.digest} data-sqlstate={code}>
      <code className={`${styles.mono} ${styles.sqlstate}`} data-tone={tone} data-testid={testId}>
        <span className={a11y.visuallyHidden}>SQLSTATE </span>
        {code}
      </code>
      {showClass || klass === 'unmodelled' ? (
        <span className={styles.sqlstateClass} data-sqlstate-class={klass}>
          {klass === 'unmodelled'
            ? `${CLASS_LABEL.unmodelled} — spec/errors.md §1.1 closes the gate path over ` +
              '{40001, 23514, 23503, 23505, P0001}'
            : CLASS_LABEL[klass]}
        </span>
      ) : null}
    </span>
  );
}
