// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE LABEL LAYER — real text, over the canvas, positioned by the frame loop.
 *
 * Two components, deliberately split across the canvas boundary:
 *
 *   `LabelLayer`     DOM. Renders one absolutely-positioned element per label, once,
 *                    and registers each element in the shared runtime. Lives OUTSIDE
 *                    the `<Canvas>`, so the text is real selectable DOM text that a
 *                    screen reader reads and a screenshot renders as glyphs.
 *   `LabelProjector` Canvas. Inside the `<Canvas>`, projects each label's world
 *                    position to screen space every frame and writes `transform` and
 *                    `opacity` straight onto the element. Renders nothing itself.
 *
 * Why not SDF text: `docs/dimensionality-charter.md` §3.1, in full. In one line, troika
 * without a `font` prop fetches a webfont, and this is the one surface whose value is
 * that it captures deterministically and serves from a static directory with no network.
 */

import { useFrame, useThree } from '@react-three/fiber';
import { useCallback, useMemo, type JSX } from 'react';
import { Vector3 } from 'three';

import type { WalkLabel } from './label-model';
import type { WalkRuntime } from './runtime';
import styles from './walk.module.css';

/** Labels closer to the camera than this are behind the reader; hide them outright. */
const NEAR_CLIP = 0.6;

/** Where a label starts fading as it recedes, in normalised device depth. */
const FADE_START = 0.985;

export interface LabelLayerProps {
  readonly labels: readonly WalkLabel[];
  readonly runtime: WalkRuntime;
}

export function LabelLayer({ labels, runtime }: LabelLayerProps): JSX.Element {
  const register = useCallback(
    (id: string) =>
      (element: HTMLElement | null): void => {
        if (element === null) {
          runtime.labelElements.delete(id);
          return;
        }
        runtime.labelElements.set(id, element);
      },
    [runtime],
  );

  return (
    <div className={styles.labels} aria-hidden="false">
      {labels.map((label) => (
        <span
          key={label.id}
          ref={register(label.id)}
          data-walk-label={label.kind}
          data-walk-label-id={label.id}
          className={`${styles.label} ${label.kind === 'still' ? styles.labelStill : styles.labelYear}`}
          // Start hidden. The first projected frame places it; an unplaced label sitting
          // at the top-left corner of the canvas for one frame is a visible artefact in
          // a capture, and a capture is the point.
          style={{ opacity: 0 }}
        >
          {label.text}
        </span>
      ))}
    </div>
  );
}

export interface LabelProjectorProps {
  readonly labels: readonly WalkLabel[];
  readonly runtime: WalkRuntime;
}

/**
 * Projects the labels. Renders nothing.
 *
 * `useFrame` at priority 1 so it runs AFTER `RailsRig` has moved the camera in the same
 * frame — a label projected against last frame's camera lags the geometry by one frame,
 * which is invisible at 60 fps and glaring in a single-frame capture.
 */
export function LabelProjector({ labels, runtime }: LabelProjectorProps): null {
  const camera = useThree((state) => state.camera);
  const size = useThree((state) => state.size);
  const scratch = useMemo(() => new Vector3(), []);

  useFrame(() => {
    for (const label of labels) {
      const element = runtime.labelElements.get(label.id);
      if (element === undefined) continue;

      scratch.set(label.position[0], label.position[1], label.position[2]);
      const distance = camera.position.distanceTo(scratch);
      scratch.project(camera);

      const behind = scratch.z > 1 || distance < NEAR_CLIP;
      if (behind) {
        element.style.opacity = '0';
        continue;
      }

      const x = (scratch.x * 0.5 + 0.5) * size.width;
      const y = (-scratch.y * 0.5 + 0.5) * size.height;
      // Rounded to whole device pixels. Sub-pixel text positions rasterise differently
      // between runs on some drivers, and this surface has a pixel baseline to keep.
      element.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`;

      const fade =
        scratch.z <= FADE_START ? 1 : Math.max(0, 1 - (scratch.z - FADE_START) / (1 - FADE_START));
      element.style.opacity = fade.toFixed(3);
    }
  }, 1);

  return null;
}
