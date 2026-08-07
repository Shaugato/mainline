// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * Meter — a neutral measurement with a marked floor.
 *
 * Built for the reading-floor meter on the disposition screen, which shows tokens
 * dispositioned and seconds elapsed against a threshold. That makes it the single most
 * dangerous component in the design package, because it is the only one that measures a
 * PERSON.
 *
 * So it is neutral by construction and the neutrality is not a default that a prop can
 * override:
 *
 *   • There is no colour that means "below the floor". No red fill, no amber track, no
 *     `data-failing` selector — none exist in `instrument.module.css` and adding one
 *     would be a design regression rather than a feature.
 *   • The floor is drawn as a hairline at its position, so the reader sees the DISTANCE
 *     to it rather than being handed a verdict about themselves.
 *   • The consequence of an unmet floor is stated in WORDS by the surface that owns the
 *     meter ("this permit now requires a countersignature from a differently-credentialed
 *     signer"), because a consequence is a fact and a colour is an accusation.
 *
 * `role="meter"` with a real `aria-valuetext` means a screen-reader user gets the
 * number and its units rather than a percentage of an unnamed thing.
 */

import { type ReactNode } from 'react';

import { useMotionAllowed } from '../motion';
import { useRegister } from '../register-context';
import styles from './instrument.module.css';

export interface MeterProps {
  readonly value: number;
  readonly min?: number;
  readonly max: number;
  /** The threshold, in the same units. Drawn as a hairline; never as a colour change. */
  readonly floor?: number;
  /** What is measured — `tokens dispositioned`, `seconds since the receipt was issued`. */
  readonly label: string;
  /** Units, shown beside the value: `tokens`, `s`. */
  readonly units?: string;
  readonly 'data-testid'?: string;
}

function fraction(value: number, min: number, max: number): number {
  if (!Number.isFinite(value) || !Number.isFinite(min) || !Number.isFinite(max) || max <= min) {
    return 0;
  }
  const clamped = Math.min(Math.max(value, min), max);
  return (clamped - min) / (max - min);
}

export function Meter({
  value,
  min = 0,
  max,
  floor,
  label,
  units,
  'data-testid': testId,
}: MeterProps): ReactNode {
  const register = useRegister();
  const animated = useMotionAllowed(register);

  const filled = fraction(value, min, max);
  const floorFraction = floor === undefined ? null : fraction(floor, min, max);
  const spokenValue = units === undefined ? `${value}` : `${value} ${units}`;
  const spokenFloor = floor === undefined ? '' : `, floor ${floor}`;

  return (
    <div className={styles.meter} data-testid={testId} data-register={register}>
      <div
        className={styles.meterTrack}
        role="meter"
        aria-label={label}
        aria-valuenow={value}
        aria-valuemin={min}
        aria-valuemax={max}
        aria-valuetext={`${spokenValue} of ${max}${spokenFloor}`}
      >
        <div
          className={styles.meterFill}
          data-animated={animated ? 'true' : 'false'}
          style={{ ['--meter-fraction' as string]: `${(filled * 100).toFixed(3)}%` }}
        />
        {floorFraction === null ? null : (
          <div
            className={styles.meterFloor}
            data-floor="true"
            style={{ ['--meter-floor' as string]: `${(floorFraction * 100).toFixed(3)}%` }}
          />
        )}
      </div>
      <div className={styles.meterCaption}>
        <span>{label}</span>
        <span>
          {value}
          {units === undefined ? null : <span className={styles.meterUnits}> {units}</span>}
          {floor === undefined ? null : (
            <span className={styles.meterUnits}>
              {' '}
              / floor {floor}
            </span>
          )}
        </span>
      </div>
    </div>
  );
}
