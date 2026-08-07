// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * StagedBadge — this value exists only in this browser.
 *
 * `BUILD_PLAN.md`'s honesty card has a STAGED column, and D7 makes it mechanical rather
 * than remembered. Nothing has been written; nothing has been refused; nobody has
 * signed anything. A staged number that reads like a committed one is the exact lie the
 * honesty chrome exists to prevent, so this badge is loud, is amber, and cannot be made
 * quiet by a prop.
 *
 * There is no `subtle`, no `size`, and no `hidden`. The only decision the caller makes
 * is whether the badge is present, and the answer to that is a fact about the value,
 * not a matter of taste.
 */

import { type ReactNode } from 'react';

import a11y from './a11y.module.css';
import styles from './chips.module.css';

export interface StagedBadgeProps {
  /**
   * What is staged, and what would have to happen for it to stop being staged —
   * "not yet POSTed to sign_disposition", "awaiting the kernel's materialise call".
   */
  readonly what: string;
  readonly 'data-testid'?: string;
}

export function StagedBadge({ what, 'data-testid': testId }: StagedBadgeProps): ReactNode {
  return (
    <span className={`${styles.chip} ${styles.staged}`} data-testid={testId} data-staged="true">
      <span className={a11y.visuallyHidden}>
        staged — not written, not refused, not signed:{' '}
      </span>
      <span aria-hidden="true">staged</span>
      <span className={styles.chipDetail}>{what}</span>
    </span>
  );
}
