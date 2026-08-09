// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE MUTABLE SEAM.
 *
 * Exactly one mutable object crosses between the DOM half of this surface (controls,
 * labels, honest notices) and the canvas half (camera, instances, projection). It is
 * declared here, in one place, so a reader can see the entire surface of shared state in
 * twenty lines and so nothing else in the directory needs a mutable module global.
 *
 * ── WHY MUTABLE AT ALL, IN A CODEBASE THIS CAREFUL ───────────────────────────────
 *
 * Because the alternative is worse. The camera moves every frame and the label layer is
 * repositioned every frame; routing either through React state re-renders the tree sixty
 * times a second, which costs the frame budget the quality ladder exists to protect and
 * makes `prefers-reduced-motion` a lie by another route.
 *
 * So per-frame values live here and are written by the frame loop and read by the frame
 * loop. Everything a HUMAN can change — which control is engaged, which detail tier is
 * in force — is React state, because those transitions are facts and belong where the
 * rest of the console can see them.
 */

import { initialRails, type RailsState } from './rails';

export interface WalkRuntime {
  /** The camera's position along the one axis. Written by `RailsRig`, read by nothing else. */
  rails: RailsState;
  /** `instanceId` of the living node under the pointer, or `null`. Never a still node. */
  hoverInstanceId: number | null;
  /** Label id → its DOM element, registered by the label layer as it mounts. */
  readonly labelElements: Map<string, HTMLElement>;
  /** How many times `advance()` has been called. Reported in `data-walk-frames-advanced`. */
  framesAdvanced: number;
}

export function createWalkRuntime(railLength: number): WalkRuntime {
  return {
    rails: initialRails(railLength),
    hoverInstanceId: null,
    labelElements: new Map<string, HTMLElement>(),
    framesAdvanced: 0,
  };
}
