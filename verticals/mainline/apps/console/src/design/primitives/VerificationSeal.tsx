// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * VerificationSeal — NEVER A GREEN TICK WITHOUT A RECOMPUTATION BEHIND IT.
 *
 * `docs/leads/ui.md` D6 is the whole design: the console re-derives, in this browser,
 * from signed bytes, every claim it displays. A seal is the visible end of that
 * arithmetic. A seal that can be rendered green by a caller passing `ok={true}` is a
 * seal that certifies a boolean, and a boolean is exactly what a React component cannot
 * authenticate.
 *
 * So the enforcement is in the TYPE, not in a code review:
 *
 *     <VerificationSeal state="verified" />                        ← does not compile
 *     <VerificationSeal state="verified" recomputation={{ … }} />   ← compiles
 *
 * `SealVerified` requires the algorithm, the instant and the digest prefix, and the
 * component renders all three next to the tick. There is no default value for
 * `recomputation`, no optional marker, and no overload that omits it. The one way to
 * get a green tick on this screen is to have done the arithmetic and to say what it
 * was.
 *
 * Four states, and `unverified` is NOT `failed`. Amber means nobody has run the
 * arithmetic yet; red means somebody ran it and it disagreed. Collapsing the two would
 * make an unchecked bundle look like a tampered one, and — far worse — would teach
 * people to ignore red.
 */

import { type ReactNode } from 'react';

import a11y from './a11y.module.css';
import styles from './chips.module.css';

/** What was recomputed, when, and over which bytes. */
export interface Recomputation {
  /** e.g. `RFC 6962 inclusion proof`, `ECDSA P-256 over the C2SP checkpoint note`. */
  readonly algorithm: string;
  /** ISO-8601 UTC instant at which THIS BROWSER finished the check. */
  readonly at: string;
  /** First characters of the digest that was checked, so the seal names its subject. */
  readonly digestPrefix: string;
}

export type SealProps =
  | {
      readonly state: 'verified';
      /** Required. There is no green tick without arithmetic behind it. */
      readonly recomputation: Recomputation;
      readonly subject: string;
      readonly 'data-testid'?: string;
    }
  | {
      readonly state: 'failed';
      /** What disagreed, verbatim. A failure with no reason is a rumour. */
      readonly reason: string;
      readonly subject: string;
      readonly 'data-testid'?: string;
    }
  | {
      readonly state: 'unverified' | 'verifying';
      /** Why it has not been checked — "bundle not loaded", "worker starting". */
      readonly reason?: string;
      readonly subject: string;
      readonly 'data-testid'?: string;
    };

const GLYPH: Readonly<Record<SealProps['state'], string>> = Object.freeze({
  verified: '✓',
  failed: '✗',
  unverified: '?',
  verifying: '…',
});

const SPOKEN: Readonly<Record<SealProps['state'], string>> = Object.freeze({
  verified: 'verified by recomputation in this browser',
  failed: 'verification FAILED',
  unverified: 'not verified — no recomputation has been run',
  verifying: 'verification in progress',
});

export function VerificationSeal(props: SealProps): ReactNode {
  const { state, subject } = props;
  return (
    <span
      className={`${styles.chip} ${styles.seal}`}
      data-state={state}
      data-testid={props['data-testid']}
      role="status"
    >
      <span className={a11y.visuallyHidden}>
        {subject}: {SPOKEN[state]}.{' '}
      </span>
      <span aria-hidden="true">{GLYPH[state]}</span>
      <span aria-hidden="true">{state}</span>
      {state === 'verified' ? (
        <span className={styles.sealDetail}>
          {props.recomputation.algorithm} · {props.recomputation.digestPrefix} ·{' '}
          {props.recomputation.at}
        </span>
      ) : state === 'failed' ? (
        <span className={styles.sealDetail}>{props.reason}</span>
      ) : props.reason === undefined ? null : (
        <span className={styles.sealDetail}>{props.reason}</span>
      )}
    </span>
  );
}
