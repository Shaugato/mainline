// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * CAMERA ON RAILS, CONSTANT VELOCITY — `docs/dimensionality-charter.md` §2.
 *
 * Half of this file is arithmetic over the state machine. The other half is a SOURCE
 * SCAN, because the rules that matter most here are absences — no orbit control, no
 * dolly zoom, no `Math.random` — and an absence is asserted by reading the bytes that
 * ship and failing on a name, not by calling a function.
 */

import { describe, expect, it } from 'vitest';

import {
  CINEMA_FRAME_SECONDS,
  RAILS_CONTROLS,
  RAIL_EYE_HEIGHT,
  RAIL_FOV_DEGREES,
  RAIL_SPEED,
  STILL_NODE_STANDOFF,
  atFarEnd,
  atPresent,
  cameraPositionFor,
  cameraTargetFor,
  directionOf,
  initialRails,
  railLengthFor,
  railsAtFrame,
  setControl,
  stepRails,
} from '../../../src/features/ancestry/render3d/rails';
import { SCENE_DEPTH } from '../../../src/features/ancestry/render3d/projection';
import { memoryCode } from './_sources';

const LENGTH = 100;

describe('there are exactly three controls', () => {
  it('and the list is the one the UI maps over', () => {
    expect(RAILS_CONTROLS).toEqual(['back', 'forward', 'stop']);
    expect(RAILS_CONTROLS).toHaveLength(3);
  });

  it('back is deeper into the past, forward is toward the present, stop is still', () => {
    expect(directionOf('back')).toBe(1);
    expect(directionOf('forward')).toBe(-1);
    expect(directionOf('stop')).toBe(0);
  });
});

describe('constant velocity', () => {
  it('moves exactly RAIL_SPEED × dt for every timestep, at every position', () => {
    let state = setControl(initialRails(LENGTH), 'back');
    const timesteps = [1 / 60, 1 / 30, 0.004, 0.25, 1 / 120, 0.05];
    for (const dt of timesteps) {
      const before = state.travel;
      state = stepRails(state, dt);
      expect(state.travel - before).toBeCloseTo(RAIL_SPEED * dt, 10);
    }
  });

  it('does not accelerate — the tenth step is the same size as the first', () => {
    let state = setControl(initialRails(1e6), 'back');
    const deltas: number[] = [];
    for (let step = 0; step < 10; step += 1) {
      const before = state.travel;
      state = stepRails(state, 1 / 60);
      deltas.push(state.travel - before);
    }
    for (const delta of deltas) {
      expect(delta).toBeCloseTo(deltas[0] ?? 0, 10);
    }
  });

  it('has NO EASING INTO THE FATALITY: the first step after a control change is full size', () => {
    // A ramped camera would move a fraction of RAIL_SPEED on the first frame after the
    // control engages. That fraction is the "cinematic" feel this surface refuses.
    const stopped = initialRails(LENGTH);
    const engaged = setControl(stopped, 'back');
    const first = stepRails(engaged, 1 / 60);
    expect(first.travel).toBeCloseTo(RAIL_SPEED / 60, 10);
  });

  it('reverses at full velocity, with no deceleration and no settle', () => {
    let state = setControl(initialRails(LENGTH), 'back');
    state = stepRails(state, 1);
    const afterBack = state.travel;
    state = setControl(state, 'forward');
    const reversed = stepRails(state, 1 / 60);
    expect(afterBack - reversed.travel).toBeCloseTo(RAIL_SPEED / 60, 10);
  });

  it('stops dead: a stopped rail does not drift', () => {
    let state = setControl(initialRails(LENGTH), 'back');
    state = stepRails(state, 0.5);
    const held = setControl(state, 'stop');
    expect(stepRails(held, 10).travel).toBe(held.travel);
  });
});

describe('the ends of the rail', () => {
  it('stops at the far end and never passes through the still node', () => {
    let state = setControl(initialRails(LENGTH), 'back');
    for (let step = 0; step < 1000; step += 1) state = stepRails(state, 1 / 60);
    expect(state.travel).toBe(LENGTH);
    expect(atFarEnd(state)).toBe(true);
  });

  it('stops at the present and never goes in front of it', () => {
    let state = setControl(initialRails(LENGTH), 'forward');
    for (let step = 0; step < 1000; step += 1) state = stepRails(state, 1 / 60);
    expect(state.travel).toBe(0);
    expect(atPresent(state)).toBe(true);
  });

  it('leaves a standoff between the camera and the fatality', () => {
    expect(railLengthFor(-SCENE_DEPTH)).toBe(SCENE_DEPTH - STILL_NODE_STANDOFF);
    expect(STILL_NODE_STANDOFF).toBeGreaterThan(0);
  });

  it('gives a single-instant ancestry a rail of length zero rather than a negative one', () => {
    expect(railLengthFor(0)).toBe(0);
    expect(railLengthFor(-1)).toBe(0);
  });

  it('ignores a non-finite or backwards timestep instead of throwing', () => {
    const state = setControl(initialRails(LENGTH), 'back');
    expect(stepRails(state, Number.NaN)).toBe(state);
    expect(stepRails(state, -1)).toBe(state);
    expect(stepRails(state, 0)).toBe(state);
  });
});

describe('the cinema position is a pure function of the frame index', () => {
  it('is exact and independent of how it was reached', () => {
    expect(railsAtFrame(0, LENGTH).travel).toBe(0);
    expect(railsAtFrame(60, LENGTH).travel).toBeCloseTo(60 * CINEMA_FRAME_SECONDS * RAIL_SPEED, 12);
    // Called twice with the same index, twice the same answer — no accumulation.
    expect(railsAtFrame(37, LENGTH)).toEqual(railsAtFrame(37, LENGTH));
  });

  it('agrees with the integrated live path to within accumulated float drift', () => {
    let live = setControl(initialRails(1e6), 'back');
    for (let step = 0; step < 600; step += 1) live = stepRails(live, CINEMA_FRAME_SECONDS);
    expect(railsAtFrame(600, 1e6).travel).toBeCloseTo(live.travel, 6);
  });

  it('clamps to the rail and refuses a nonsense frame index', () => {
    expect(railsAtFrame(1e9, LENGTH).travel).toBe(LENGTH);
    expect(railsAtFrame(-5, LENGTH).travel).toBe(0);
    expect(railsAtFrame(Number.NaN, LENGTH).travel).toBe(0);
  });
});

describe('one degree of freedom', () => {
  it('varies z and nothing else', () => {
    const near = cameraPositionFor(initialRails(LENGTH));
    const far = cameraPositionFor({ travel: 40, control: 'back', railLength: LENGTH });
    expect(near[0]).toBe(far[0]);
    expect(near[1]).toBe(far[1]);
    expect(near[1]).toBe(RAIL_EYE_HEIGHT);
    expect(far[2]).toBeLessThan(near[2]);
  });

  it('looks straight down the rail at a constant height — no tilt, no tracking', () => {
    for (const travel of [0, 12, 55, LENGTH]) {
      const state = { travel, control: 'back' as const, railLength: LENGTH };
      const position = cameraPositionFor(state);
      const target = cameraTargetFor(state);
      expect(target[0]).toBe(position[0]);
      expect(target[1]).toBe(position[1]);
      expect(target[2]).toBe(position[2] - 1);
    }
  });

  it('declares the field of view as a constant', () => {
    expect(RAIL_FOV_DEGREES).toBeGreaterThan(0);
    expect(Number.isFinite(RAIL_FOV_DEGREES)).toBe(true);
  });
});

describe('the absences, read out of the shipped source', () => {
  const sources = memoryCode();

  /** Every camera helper that would give the reader a second degree of freedom. */
  const CAMERA_HELPERS = [
    'OrbitControls',
    'MapControls',
    'TrackballControls',
    'FlyControls',
    'FirstPersonControls',
    'PointerLockControls',
    'PresentationControls',
    'ScrollControls',
    'CameraControls',
    'CameraShake',
    'useCamera',
  ];

  it('imports no camera helper from drei or anywhere else', () => {
    for (const [path, code] of Object.entries(sources)) {
      for (const helper of CAMERA_HELPERS) {
        expect(`${path}: ${code}`).not.toContain(helper);
      }
    }
  });

  it('never writes a camera field of view — there is no dolly zoom to write', () => {
    for (const [path, code] of Object.entries(sources)) {
      expect(path + code).not.toMatch(/\.fov\b/);
      expect(path + code).not.toMatch(/setFocalLength/);
    }
  });

  it('never writes a camera rotation, quaternion or up vector directly', () => {
    for (const [path, code] of Object.entries(sources)) {
      expect(path + code).not.toMatch(/camera\.(rotation|quaternion|up|zoom)\b/);
    }
  });

  it('calls Math.random nowhere — there is no non-deterministic value in this scene', () => {
    for (const [path, code] of Object.entries(sources)) {
      expect(`${path}: ${code}`).not.toContain('Math.random');
    }
  });

  it('reads no wall clock in the geometry path', () => {
    for (const [path, code] of Object.entries(sources)) {
      if (path.endsWith('/cinema.ts')) continue; // parses a frozen ISO instant; never reads one
      expect(`${path}: ${code}`).not.toContain('Date.now(');
      expect(`${path}: ${code}`).not.toContain('performance.now(');
    }
  });

  it('scans a non-trivial number of files — a scan over nothing passes vacuously', () => {
    expect(Object.keys(sources).length).toBeGreaterThanOrEqual(12);
  });
});
