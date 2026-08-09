// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE RAILS — the camera's entire degree of freedom.
 *
 * `docs/leads/ui.md` §1.2.2:
 *
 *   > Camera on rails, constant velocity. No easing into a fatality, no dolly zoom, no
 *   > orbit. The walk is a walk. The user's only controls are *further back* and
 *   > *further forward* along one axis, plus a stop.
 *
 * This module is that rule as a pure state machine. It has no React, no three.js and no
 * clock; `RailsRig.tsx` is a thin adapter that calls `stepRails` once per frame and
 * writes the result onto a camera. Everything interesting is testable without a GPU,
 * which is the only reason the interesting things have tests.
 *
 * ── WHY CONSTANT VELOCITY IS A RULE AND NOT A PREFERENCE ─────────────────────────
 *
 * An eased camera decides, on the reader's behalf, which part of the walk deserves
 * emphasis. Easing into the terminal node makes the fatality feel like an arrival — a
 * beat in a film. It is not a beat. It is where somebody died, and it is reached at the
 * same speed as every other year, because the twenty-two years in front of it are not
 * an approach shot.
 *
 * The mechanism also buys determinism: position is `travel = speed × elapsed`, so under
 * cinema mode `railsAtFrame(n)` is exact, has no accumulated float error, and does not
 * depend on the order or timing of the frames that preceded it (charter §5, D3).
 */

/** The three controls. There is no fourth (charter §2, R1). */
export type RailsControl = 'back' | 'forward' | 'stop';

export const RAILS_CONTROLS: readonly RailsControl[] = ['back', 'forward', 'stop'];

/** World units per second. One constant, used in both directions, never scaled. */
export const RAIL_SPEED = 9;

/**
 * The cinema-mode timestep.
 *
 * 1/60 s exactly. Chosen because it is the only value that makes `railsAtFrame(n)`
 * reproducible from a `?frame=` integer on a machine whose real frame rate is whatever
 * SwiftShader manages that afternoon. The captured walk is a function of the frame
 * INDEX, never of the runner's clock.
 */
export const CINEMA_FRAME_SECONDS = 1 / 60;

/**
 * How far short of the still node the camera stops.
 *
 * The design decision under the mechanism: the reader is brought to the fatality and
 * stopped short of it. They may look; they may not arrive.
 */
export const STILL_NODE_STANDOFF = 11;

/**
 * The camera's fixed field of view, in degrees.
 *
 * A module constant with no setter anywhere in this directory. That is what "no dolly
 * zoom" means mechanically: there is no code path that writes a camera's `fov`, so the
 * one visual effect that would make the walk feel cinematic is not merely unused, it is
 * unreachable (charter §2, R4).
 */
export const RAIL_FOV_DEGREES = 42;

/**
 * How far above the rail's own axis the camera sits, and how far up it looks.
 *
 * Both fixed. The camera does not tilt, does not roll, and does not track a node.
 */
export const RAIL_EYE_HEIGHT = 2.4;

export interface RailsState {
  /**
   * Distance travelled back along the time axis, in world units. `0` is the present;
   * `railLength` is the far end of the walk. Never negative, never beyond the end.
   */
  readonly travel: number;
  readonly control: RailsControl;
  /** The length of the rail, in world units. Fixed for the life of a scene. */
  readonly railLength: number;
}

/**
 * The rail's length for a scene.
 *
 * `deepestZ` is negative (older is further away), so the raw depth is `-deepestZ`. The
 * standoff is subtracted so the camera stops short of the oldest node rather than
 * inside it, and the result is clamped at zero: a single-instant ancestry has a rail of
 * length zero, and a walk with nowhere to walk is honest about it.
 */
export function railLengthFor(deepestZ: number): number {
  return Math.max(0, -deepestZ - STILL_NODE_STANDOFF);
}

export function initialRails(railLength: number): RailsState {
  return { travel: 0, control: 'stop', railLength: Math.max(0, railLength) };
}

/**
 * Sets the control. Instantaneous — there is no ramp, no blend and no "was moving
 * forward, so decelerate first". A relay closes or it does not.
 */
export function setControl(state: RailsState, control: RailsControl): RailsState {
  return { travel: state.travel, control, railLength: state.railLength };
}

/** `+1` deeper into the past, `−1` toward the present, `0` stopped. */
export function directionOf(control: RailsControl): -1 | 0 | 1 {
  if (control === 'back') return 1;
  if (control === 'forward') return -1;
  return 0;
}

/**
 * One step. `travel += direction × RAIL_SPEED × dt`, clamped to the rail.
 *
 * There is no acceleration term, no easing function and no interpolation toward a
 * target. `rails.test.ts` asserts the equality directly for a sequence of arbitrary
 * timesteps, which is what makes "constant velocity" a measured property rather than a
 * described one.
 *
 * A non-finite or negative `dt` is treated as zero rather than throwing: a dropped frame
 * or a clock that went backwards should freeze the walk, not take down the canvas.
 */
export function stepRails(state: RailsState, dtSeconds: number): RailsState {
  if (!Number.isFinite(dtSeconds) || dtSeconds <= 0) return state;
  const direction = directionOf(state.control);
  if (direction === 0) return state;
  const next = state.travel + direction * RAIL_SPEED * dtSeconds;
  const clamped = Math.min(state.railLength, Math.max(0, next));
  if (clamped === state.travel) return state;
  return { travel: clamped, control: state.control, railLength: state.railLength };
}

/**
 * THE CINEMA POSITION. `travel` as a pure function of an integer frame index.
 *
 * Not `stepRails` applied `n` times: repeated addition of `RAIL_SPEED × 1/60` accumulates
 * a different float than one multiplication, and "different by one ulp" is a different
 * screenshot. The capture uses this; the live loop uses `stepRails`; `rails.test.ts`
 * asserts they agree to within a tolerance that names the ulp drift explicitly.
 */
export function railsAtFrame(frame: number, railLength: number): RailsState {
  const whole = Number.isFinite(frame) ? Math.max(0, Math.trunc(frame)) : 0;
  const travel = Math.min(Math.max(0, railLength), whole * CINEMA_FRAME_SECONDS * RAIL_SPEED);
  // A capture is a still: the control that produced the position is 'back' by
  // construction, because a capture walks into the past and nothing else.
  return { travel, control: 'back', railLength: Math.max(0, railLength) };
}

/** Whether the camera has reached the far end and can go no deeper. */
export function atFarEnd(state: RailsState): boolean {
  return state.railLength > 0 && state.travel >= state.railLength;
}

export function atPresent(state: RailsState): boolean {
  return state.travel <= 0;
}

/**
 * The camera's world position for a rails state.
 *
 * One axis. `x` and `y` are constants; only `z` is a function of `travel`. This is the
 * literal expression of "one degree of freedom" — the return type could not carry an
 * orbit even if a caller wanted one.
 */
export function cameraPositionFor(state: RailsState): readonly [number, number, number] {
  return [0, RAIL_EYE_HEIGHT, -state.travel];
}

/**
 * Where the camera looks: straight down the rail, at the same height it sits at.
 *
 * Fixed offset, so the look direction is constant for the whole walk. No tracking, no
 * lead-in, no framing of the terminal node as it approaches.
 */
export function cameraTargetFor(state: RailsState): readonly [number, number, number] {
  return [0, RAIL_EYE_HEIGHT, -state.travel - 1];
}
