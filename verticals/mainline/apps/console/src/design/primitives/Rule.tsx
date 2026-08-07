// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Rule — a horizontal line, and a decision about whether it means anything.
 *
 * Two variants, because WCAG 2.2 SC 1.4.11 draws exactly this distinction and the
 * console should not have to guess which side a given line is on:
 *
 *   `separator` — a row divider inside a table or list. It carries no information; the
 *                 rows are already separated by position and content. Floored at 1.2:1
 *                 in `pairs.ts` only so it cannot become invisible and stop separating
 *                 anything. The exemption is written down with its reason rather than
 *                 granted by leaving the token out of the contrast gate.
 *
 *   `section`   — a break between parts of a document. It DOES carry information, so it
 *                 meets the 3:1 non-text floor and it is announced as a separator.
 *
 * Choosing between them is the caller's one decision, and there is no third option that
 * means "make it look nicer".
 */

import { type ReactNode } from 'react';

import styles from './frame.module.css';

export interface RuleProps {
  readonly variant?: 'separator' | 'section';
  readonly 'data-testid'?: string;
}

export function Rule({ variant = 'separator', 'data-testid': testId }: RuleProps): ReactNode {
  return (
    <hr
      className={variant === 'section' ? `${styles.rule} ${styles.ruleStrong}` : styles.rule}
      data-variant={variant}
      data-testid={testId}
      // A decorative separator is hidden from assistive technology: announcing "separator"
      // between every row of a fifty-row table is noise that makes the meaningful one
      // impossible to hear.
      aria-hidden={variant === 'separator' ? 'true' : undefined}
    />
  );
}
