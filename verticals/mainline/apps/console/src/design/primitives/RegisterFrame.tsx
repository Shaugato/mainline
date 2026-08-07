// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * RegisterFrame — the register, declared on the tree.
 *
 * The import boundary (`registers.ts` + the ESLint fragment + `register-boundary.test.ts`)
 * decides what a DIRECTORY may depend on. This frame decides what a component INSTANCE
 * may do, and those are genuinely different questions: `Counter` is one file that is an
 * INSTRUMENT inside the propagation surface and EVIDENCE inside the refusal bar. No
 * directory rule can express that.
 *
 * The frame writes `data-register` onto the DOM, which means:
 *   • `Counter` and `Meter` read it and decide whether they may move;
 *   • a Playwright spec can assert the law a subtree was operating under; and
 *   • a captured DOM in an evidence bundle carries the same fact, so a reviewer looking
 *     at a screenshot months later can tell which rules applied.
 */

import { type ReactNode } from 'react';

import { RegisterContext } from '../register-context';
import { type Register } from '../registers';
import styles from './frame.module.css';

export interface RegisterFrameProps {
  readonly register: Register;
  readonly children: ReactNode;
  /** Draws the panel edge and padding. Off by default — a frame is semantics first. */
  readonly bordered?: boolean;
  /** An uppercase caption above the frame, e.g. the panel's name. */
  readonly label?: string;
  /** `section` when the frame is a landmark with a label; `div` otherwise. */
  readonly as?: 'div' | 'section';
  readonly className?: string;
  readonly 'data-testid'?: string;
}

export function RegisterFrame({
  register,
  children,
  bordered = false,
  label,
  as = 'div',
  className,
  'data-testid': testId,
}: RegisterFrameProps): ReactNode {
  const classes = [styles.frame, bordered ? styles.frameBordered : null, className]
    .filter((entry) => entry !== null && entry !== undefined && entry !== '')
    .join(' ');

  const body = (
    <>
      {label === undefined ? null : <span className={styles.frameLabel}>{label}</span>}
      {children}
    </>
  );

  return (
    <RegisterContext.Provider value={register}>
      {as === 'section' ? (
        <section className={classes} data-register={register} data-testid={testId} aria-label={label}>
          {body}
        </section>
      ) : (
        <div className={classes} data-register={register} data-testid={testId}>
          {body}
        </div>
      )}
    </RegisterContext.Provider>
  );
}
