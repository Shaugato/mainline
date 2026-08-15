// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE WAIT IS REAL, AND IT IS THE SHOT.
 *
 * `POST /v1/demo/gate-run` opens a SERIALIZABLE transaction, plays four beats against a
 * real CockroachDB node and rolls the whole thing back. It takes roughly 2.5 s warm and
 * up to 9 s on a cold Lambda. That wait is the product doing the thing the product does —
 * it is not a defect to hide behind an optimistic render.
 *
 * So this module drives the pending state from the REAL PROMISE and shows a REAL ELAPSED
 * CLOCK, and it contains:
 *
 *   * **no scheduled delay** — not a timeout, not an interval, not a minimum spinner
 *     duration, not for anything. Neither scheduling primitive is named anywhere in this
 *     directory, and a unit test greps the shipped source text for both;
 *   * **no optimistic state** — nothing is rendered as done before the promise settles;
 *   * **no skeleton that pretends to be work** — the only thing that moves is a counter
 *     reading a real clock, and the label says whose clock it is.
 *
 * The elapsed number here is the CLIENT's round-trip measurement. It is deliberately kept
 * distinct from the payload's per-beat `elapsed_ms`, which is the SERVER's measurement of
 * the statement itself; `beats.ts` renders those and never this one. Two clocks, two
 * labels, never mixed.
 *
 * Ticking uses `requestAnimationFrame`, which schedules a repaint and samples the clock —
 * it manufactures no duration. Where it does not exist (a non-browser host), the counter
 * simply does not animate and the final elapsed is still the true measured one.
 */

/** The two host capabilities this module needs, injectable so a test can drive them. */
export interface ClockHost {
  /** Monotonic milliseconds. */
  now(): number;
  /** Schedule one callback for the next repaint. Returns a cancellation handle. */
  frame(callback: () => void): number;
  cancelFrame(handle: number): void;
}

/** The real host. `performance.now()` is monotonic; `Date.now()` is not. */
export const browserClock: ClockHost = {
  now: () =>
    typeof performance !== 'undefined' && typeof performance.now === 'function'
      ? performance.now()
      : Date.now(),
  frame: (callback) =>
    typeof requestAnimationFrame === 'function' ? requestAnimationFrame(() => { callback(); }) : 0,
  cancelFrame: (handle) => {
    if (handle !== 0 && typeof cancelAnimationFrame === 'function') cancelAnimationFrame(handle);
  },
};

export type PendingPhase = 'idle' | 'in_flight' | 'settled';

export interface PendingState {
  readonly phase: PendingPhase;
  /**
   * Milliseconds since the request was sent, from the host clock. While in flight this is
   * the live reading; once settled it is the final one. It is never estimated.
   */
  readonly elapsedMs: number;
  /** True when the promise rejected. A transport failure is not a refusal. */
  readonly failed: boolean;
}

export interface PendingController {
  readonly state: PendingState;
  /**
   * Drives the pending state off `work` and returns it unchanged — the caller still awaits
   * the same promise and still sees the same rejection. This wrapper decides nothing.
   */
  track<T>(work: Promise<T>): Promise<T>;
  subscribe(listener: (state: PendingState) => void): () => void;
}

const IDLE: PendingState = { phase: 'idle', elapsedMs: 0, failed: false };

export function createPending(host: ClockHost = browserClock): PendingController {
  let state: PendingState = IDLE;
  let startedAt = 0;
  let frameHandle = 0;
  const listeners = new Set<(state: PendingState) => void>();

  const publish = (next: PendingState): void => {
    state = next;
    for (const listener of listeners) listener(state);
  };

  const tick = (): void => {
    if (state.phase !== 'in_flight') return;
    publish({ phase: 'in_flight', elapsedMs: host.now() - startedAt, failed: false });
    frameHandle = host.frame(tick);
  };

  const stopTicking = (): void => {
    host.cancelFrame(frameHandle);
    frameHandle = 0;
  };

  return {
    get state(): PendingState {
      return state;
    },
    track<T>(work: Promise<T>): Promise<T> {
      startedAt = host.now();
      publish({ phase: 'in_flight', elapsedMs: 0, failed: false });
      frameHandle = host.frame(tick);
      return work.then(
        (value) => {
          stopTicking();
          publish({ phase: 'settled', elapsedMs: host.now() - startedAt, failed: false });
          return value;
        },
        (reason: unknown) => {
          stopTicking();
          publish({ phase: 'settled', elapsedMs: host.now() - startedAt, failed: true });
          throw reason;
        },
      );
    },
    subscribe(listener): () => void {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

/**
 * What the button says while the database is deciding.
 *
 * It names the transaction rather than describing a mood, and it carries the clock's owner
 * so the number cannot be mistaken for a server measurement.
 */
export function pendingLabel(state: PendingState): string {
  if (state.phase !== 'in_flight') return '';
  const seconds = (state.elapsedMs / 1000).toFixed(1);
  return `Issuing… ${seconds} s`;
}

/** The line beside the button while in flight. One sentence, all of it true. */
export const PENDING_NOTE =
  'One SERIALIZABLE transaction is open against the database. The clock is this browser’s ' +
  'measurement of the round trip; each beat below reports the duration the server measured.';
