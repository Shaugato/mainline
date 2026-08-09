// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE RIG — the only thing in this directory that touches a camera.
 *
 * It is a thin adapter over `rails.ts`, and thin is the specification: every decision
 * about how the camera behaves is a pure function tested without a GPU, and this file
 * only chooses which of them to call and writes the result.
 *
 * What it does NOT do is the interesting part (charter §2):
 *
 *   • It never writes `camera.fov`. There is no dolly zoom because there is no line of
 *     code that could produce one.
 *   • It never writes `camera.rotation`, `camera.up` or `camera.quaternion` directly —
 *     `lookAt` down the rail at a fixed height, every frame, identically.
 *   • It never eases. `stepRails` is `travel += ±speed × dt`, full stop.
 *   • Under cinema mode it does not integrate at all: the camera position is
 *     `railsAtFrame(frame)`, a pure function of one integer, so the rendered image is a
 *     function of `?frame=` and of nothing else — not of how many frames preceded it,
 *     not of the runner's clock, not of accumulated float drift.
 */

import { useFrame, useThree } from '@react-three/fiber';

import { cameraPositionFor, cameraTargetFor, railsAtFrame, stepRails } from './rails';
import type { WalkRuntime } from './runtime';

export interface RailsRigProps {
  readonly runtime: WalkRuntime;
  /** The frame index under cinema mode, or `null` when the walk is live. */
  readonly cinemaFrame: number | null;
  /** Receives each frame's wall duration in milliseconds. Feeds the quality ladder. */
  readonly onSample: (frameMs: number) => void;
}

export function RailsRig({ runtime, cinemaFrame, onSample }: RailsRigProps): null {
  const camera = useThree((state) => state.camera);

  useFrame((_state, delta) => {
    runtime.framesAdvanced += 1;

    if (cinemaFrame === null) {
      runtime.rails = stepRails(runtime.rails, delta);
      // `delta` is the real interval the reader experienced, which is exactly what the
      // ladder is grading. Under cinema mode it is meaningless and is not sampled.
      onSample(delta * 1000);
    } else {
      runtime.rails = railsAtFrame(cinemaFrame, runtime.rails.railLength);
    }

    const [px, py, pz] = cameraPositionFor(runtime.rails);
    const [tx, ty, tz] = cameraTargetFor(runtime.rails);
    camera.position.set(px, py, pz);
    camera.lookAt(tx, ty, tz);
  }, 0);

  return null;
}
