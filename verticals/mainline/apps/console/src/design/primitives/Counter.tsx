// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Counter — a number the database reported, and the one moment it is allowed to move.
 *
 * `docs/leads/ui.md` §1.1, INSTRUMENT register: motion is permitted only where THE
 * TRANSITION IS THE FACT. `open_blocking` going 1 → 0 is the product working; marking
 * that instant reports something true. Nothing else here animates — not the mount, not
 * a hover, not a re-render that produced the same number.
 *
 * Three rules the implementation makes structural rather than remembered:
 *
 *   1. The register comes from the surrounding `RegisterFrame`, not from a prop. Drop
 *      this component into the refusal bar and it is EVIDENCE and it does not move;
 *      drop it into the propagation surface and it is an INSTRUMENT and it does. One
 *      file, two behaviours, decided by the tree rather than by whoever is writing the
 *      call site.
 *   2. The default register is `evidence`, so a Counter rendered outside any frame does
 *      not move. The safe answer is the default answer.
 *   3. The end state is IDENTICAL whether or not the transition ran. The mark is a
 *      `data-transition` attribute that appears for one duration and is removed; the
 *      number itself is set synchronously, always. There is no tween over the value —
 *      a counter that rolls 7 → 6 → 5 → … displays four numbers the database never
 *      reported, which on an evidentiary surface is four small lies.
 */

import { useEffect, useRef, useState, type ReactNode } from 'react';

import { DURATION_MS, useMotionAllowed } from '../motion';
import { useRegister } from '../register-context';
import a11y from './a11y.module.css';
import styles from './instrument.module.css';

export type CounterDirection = 'up' | 'down';

export interface CounterProps {
  /** The value, exactly as reported. Rendered synchronously; never tweened. */
  readonly value: number;
  /** What is being counted — `open blocking checks`, `sites that declined`. */
  readonly label: string;
  /**
   * Where the number came from. A Counter with no provenance is a number the console
   * appears to have produced, so the chip is rendered by the surface beside this
   * component and this component refuses to invent one.
   */
  readonly children?: ReactNode;
  readonly 'data-testid'?: string;
}

export function Counter({
  value,
  label,
  children,
  'data-testid': testId,
}: CounterProps): ReactNode {
  const register = useRegister();
  const motionAllowed = useMotionAllowed(register);

  const previous = useRef<number | null>(null);
  const [direction, setDirection] = useState<CounterDirection | null>(null);

  useEffect(() => {
    const before = previous.current;
    previous.current = value;
    if (before === null || before === value) return undefined;
    if (!motionAllowed) return undefined;

    setDirection(value < before ? 'down' : 'up');
    const timer = setTimeout(() => {
      setDirection(null);
    }, DURATION_MS.instrument);
    return () => {
      clearTimeout(timer);
    };
  }, [value, motionAllowed]);

  return (
    <span className={styles.counter} data-testid={testId} data-register={register}>
      <span
        className={styles.counterValue}
        // Absent entirely when motion is refused, so the selector cannot match and a
        // screenshot of a reduced-motion session is byte-comparable with an animated one
        // at rest.
        data-transition={direction ?? undefined}
      >
        {value}
      </span>
      <span className={styles.counterLabel}>
        {label}
        {direction === null ? null : (
          <span className={a11y.visuallyHidden}>
            {' '}
            (just changed {direction === 'down' ? 'downwards' : 'upwards'})
          </span>
        )}
      </span>
      {children}
    </span>
  );
}
