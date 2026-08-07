// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * ConstraintName — the identifier the database refused under.
 *
 * This is the most valuable string on the gate screen. `gate_closed_when_issued` is not
 * a label the console composed; it is the name of a CHECK constraint that a reader can
 * grep for in `verticals/mainline/db/migrations/` and find the SQL that refused their
 * write. That is the difference between a refusal and an error message.
 *
 * Consequences that are enforced here rather than remembered:
 *
 *   • The value is rendered verbatim. No case change, no underscore-to-space, no
 *     "friendly" rewriting. `docs/leads/ui.md` D18 — a prettified refusal is a
 *     different refusal.
 *   • It is selectable text in the mono face, never an image.
 *   • The component takes no `label` or `description` prop. There is nowhere to put a
 *     sentence the console made up, which is the only reliable way to stop one
 *     appearing.
 */

import { type ReactNode } from 'react';

import a11y from './a11y.module.css';
import styles from './verbatim.module.css';

export interface ConstraintNameProps {
  /** The constraint identifier exactly as the database reported it. */
  readonly name: string;
  /**
   * `refuse` gives the accent, the emphasis weight and the emphasis size — for the
   * constraint that is the subject of the refusal on screen. Default `neutral`, because
   * most constraint names on a screen are context rather than the verdict.
   */
  readonly tone?: 'neutral' | 'refuse';
  readonly 'data-testid'?: string;
}

export function ConstraintName({
  name,
  tone = 'neutral',
  'data-testid': testId,
}: ConstraintNameProps): ReactNode {
  return (
    <code
      className={`${styles.mono} ${styles.constraint}`}
      data-tone={tone}
      data-constraint={name}
      data-testid={testId}
    >
      <span className={a11y.visuallyHidden}>constraint </span>
      {name}
    </code>
  );
}
