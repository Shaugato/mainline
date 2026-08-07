// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE MOTION POLICY.
 *
 * One easing set, two ceilings, and one hook that can say no.
 *
 * `docs/leads/ui.md` §1.1 permits motion in exactly one circumstance: *the transition
 * IS the fact*. A counter of open blocking checks going 1 → 0 is the product working,
 * and animating that transition reports something true. Everything else — a panel
 * sliding in, a card fading up, a number counting for flavour — reports nothing, costs
 * a frame budget, and makes a screenshot an incomplete rendering of the screen.
 *
 * ── WHY THERE IS NO ANIMATION LIBRARY HERE ───────────────────────────────────────
 *
 * `motion` (MIT) is a dependency of this workspace and is legal in the INSTRUMENT and
 * MEMORY registers. It is deliberately NOT used by `src/design/`.
 *
 * The reason is the register boundary itself. Every EVIDENCE surface imports these
 * primitives. If `Counter.tsx` imported `motion`, then `src/features/gate/` would
 * transitively import `motion` — the exact thing D9 forbids — while every ESLint rule
 * stayed green, because the forbidden import would sit in a directory that is allowed
 * to have it. The boundary would be dead and nothing would say so.
 *
 * So the design package is register-neutral: CSS transitions, `useMotionAllowed()`, and
 * no library. `register-boundary.test.ts` asserts it.
 */

import { useSyncExternalStore } from 'react';

import { CAPABILITY } from '../app/capability';
import { type Register } from './registers';

// ── Ceilings ─────────────────────────────────────────────────────────────────────

/** EVIDENCE: 160 ms. Above this, a transition outlives the eye's tolerance for a document. */
export const EVIDENCE_CEILING_MS = 160;

/** INSTRUMENT and MEMORY: 220 ms. The hard ceiling for the whole console. */
export const INSTRUMENT_CEILING_MS = 220;

/** No register in this console may exceed this, ever. */
export const ABSOLUTE_CEILING_MS = INSTRUMENT_CEILING_MS;

export function ceilingFor(register: Register): number {
  return register === 'evidence' ? EVIDENCE_CEILING_MS : INSTRUMENT_CEILING_MS;
}

// ── Durations ────────────────────────────────────────────────────────────────────

/**
 * The permitted durations, in milliseconds, matching `tokens.css` exactly.
 * `motion.test.ts` parses the stylesheet and asserts the two agree — a duration that
 * drifts between the CSS and the TypeScript is a policy with two answers.
 */
export const DURATION_MS = Object.freeze({
  evidence: 120,
  instrument: 200,
});

// ── Easing ───────────────────────────────────────────────────────────────────────

/**
 * THE ENTIRE PERMITTED EASING SET. Two entries.
 *
 * `linear` is the default, and that is a statement rather than laziness: a measurement
 * does not accelerate. A counter that eases out is performing confidence it has not
 * earned.
 *
 * `mechanical` is a single cubic with a zero-slope start and a settled finish — the
 * motion of a relay closing. It has no overshoot and no rebound, because an overshoot
 * shows a value the data never held, and on a screen whose numbers are evidentiary,
 * showing a value the data never held is a small lie told sixty times a second.
 *
 * There is no spring. Springs are parameterised by mass and stiffness, which means the
 * peak value depends on the interruption history — and an interrupted spring is
 * non-deterministic under the cinema-mode capture D12 requires.
 */
export const EASING = Object.freeze({
  linear: 'linear',
  mechanical: 'cubic-bezier(0.2, 0, 0.38, 1)',
});

export type EasingName = keyof typeof EASING;

export const EASING_NAMES: readonly EasingName[] = ['linear', 'mechanical'];

// ── The gate ─────────────────────────────────────────────────────────────────────

const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)';

/**
 * Why motion is off, or `null` when it is on. Rendered verbatim where a reader might
 * otherwise wonder whether the console is broken.
 */
export type MotionRefusal = string | null;

/**
 * The low-power half of the decision, read once from the capability probe.
 *
 * `CAPABILITY` is a frozen snapshot taken at module load (see `app/capability.ts`), so
 * these signals do not change under the reader mid-session. The reduced-motion media
 * query DOES change — a reader can toggle it in OS settings with the console open — so
 * it is subscribed live below rather than snapshotted here.
 *
 * `deviceMemoryGb === null` is NOT low. A browser that does not implement
 * `navigator.deviceMemory` has told us nothing, and inventing a number for it would be
 * a fabricated claim about the reader's machine.
 */
function lowPowerRefusal(): MotionRefusal {
  if (CAPABILITY.saveData) {
    return 'save-data is set on this connection — the console does not spend a frame budget a reader asked it not to spend.';
  }
  if (CAPABILITY.deviceMemoryGb !== null && CAPABILITY.deviceMemoryGb < 4) {
    return `navigator.deviceMemory reports ${CAPABILITY.deviceMemoryGb} GB, below the 4 GB floor — transitions are skipped and every end state is unchanged.`;
  }
  return null;
}

function subscribeReducedMotion(onChange: () => void): () => void {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return () => undefined;
  }
  const query = window.matchMedia(REDUCED_MOTION_QUERY);
  query.addEventListener('change', onChange);
  return () => {
    query.removeEventListener('change', onChange);
  };
}

function readReducedMotion(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false;
  return window.matchMedia(REDUCED_MOTION_QUERY).matches;
}

/** The server snapshot. No window ⇒ no motion; a static render is a still image. */
function readReducedMotionServer(): boolean {
  return true;
}

/**
 * The whole decision, as a pure function of the two signals. Exported so that
 * `motion.test.ts` can exercise every combination without a browser and without
 * mocking React.
 */
export function decideMotion(
  register: Register,
  prefersReducedMotion: boolean,
  lowPower: MotionRefusal,
): { readonly allowed: boolean; readonly refusal: MotionRefusal } {
  if (prefersReducedMotion) {
    return {
      allowed: false,
      refusal:
        'prefers-reduced-motion is set — every transition is skipped and every end state is identical to the animated one.',
    };
  }
  if (lowPower !== null) {
    return { allowed: false, refusal: lowPower };
  }
  if (register === 'evidence') {
    return {
      allowed: false,
      refusal:
        'EVIDENCE register — nothing moves that a screenshot could not reproduce (docs/leads/ui.md §1.1).',
    };
  }
  return { allowed: true, refusal: null };
}

/**
 * Whether the calling component may animate.
 *
 * Defaults to the EVIDENCE register, which answers `false`. That default is the
 * important part: a component that forgot to declare its register gets the answer that
 * cannot be wrong, rather than the answer that is convenient.
 *
 * Live-subscribes to `prefers-reduced-motion` so that toggling it mid-session takes
 * effect without a reload — a reader who turns reduced motion on has usually just been
 * made unwell by something moving, and telling them to refresh is not an answer.
 */
export function useMotionAllowed(register: Register = 'evidence'): boolean {
  const reduced = useSyncExternalStore(
    subscribeReducedMotion,
    readReducedMotion,
    readReducedMotionServer,
  );
  return decideMotion(register, reduced, lowPowerRefusal()).allowed;
}

/** The same decision plus the sentence explaining it, for surfaces that show their arithmetic. */
export function useMotionPolicy(register: Register = 'evidence'): {
  readonly allowed: boolean;
  readonly refusal: MotionRefusal;
  readonly ceilingMs: number;
} {
  const reduced = useSyncExternalStore(
    subscribeReducedMotion,
    readReducedMotion,
    readReducedMotionServer,
  );
  const decision = decideMotion(register, reduced, lowPowerRefusal());
  return { allowed: decision.allowed, refusal: decision.refusal, ceilingMs: ceilingFor(register) };
}

/**
 * Builds a `transition` shorthand, refusing anything over the register's ceiling.
 *
 * It THROWS rather than clamping. A clamped duration is a policy violation that ships;
 * a thrown one is a policy violation that fails a unit test the first time it is
 * written, which is the only moment it is cheap to fix.
 */
export function transition(
  property: string,
  register: Register,
  options: { readonly durationMs?: number; readonly easing?: EasingName } = {},
): string {
  const ceiling = ceilingFor(register);
  const durationMs =
    options.durationMs ?? (register === 'evidence' ? DURATION_MS.evidence : DURATION_MS.instrument);
  if (durationMs > ceiling) {
    throw new Error(
      `motion.ts: ${durationMs}ms exceeds the ${register.toUpperCase()} ceiling of ${ceiling}ms ` +
        `(docs/leads/ui.md §1.1). Shorten it, or move the component to a register that permits it.`,
    );
  }
  if (durationMs < 0 || !Number.isFinite(durationMs)) {
    throw new Error(`motion.ts: ${durationMs}ms is not a duration.`);
  }
  const easing = EASING[options.easing ?? 'linear'];
  return `${property} ${durationMs}ms ${easing}`;
}
