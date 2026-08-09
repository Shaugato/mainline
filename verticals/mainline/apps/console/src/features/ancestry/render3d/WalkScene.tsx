// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE SCENE.
 *
 * Mounts what `objects.ts` built, wires the one interaction the surface has, and adds
 * nothing else. In particular it adds:
 *
 *   • no light — `<ambientLight>`, `<directionalLight>` and every other light are absent,
 *     which is what makes "never emits" a property of the scene rather than of one node
 *     (charter §1, S8 and §3, P6);
 *   • no fog, no environment, no background texture, no skybox;
 *   • no `OrbitControls`, `CameraControls`, `PresentationControls` or any other camera
 *     helper — the camera has one degree of freedom and `RailsRig` owns it;
 *   • no post-processing pass of any kind.
 *
 * `rails.test.ts` and `palette.test.ts` scan this directory's source for each of those
 * names, so the absences above are enforced rather than described.
 */

import { type ThreeEvent } from '@react-three/fiber';
import { useCallback, useEffect, useMemo, type JSX } from 'react';

import type { AnimationRegistry } from './animation-registry';
import type { WalkLabel } from './label-model';
import { LabelProjector } from './Labels';
import { createWalkObjects, writeHoverScale } from './objects';
import type { PaletteHex } from './palette';
import type { WalkScene as WalkSceneModel } from './projection';
import { RailsRig } from './RailsRig';
import type { WalkRuntime } from './runtime';

export interface WalkSceneProps {
  readonly scene: WalkSceneModel;
  readonly palette: PaletteHex;
  readonly registry: AnimationRegistry;
  readonly runtime: WalkRuntime;
  readonly labels: readonly WalkLabel[];
  readonly laneRails: boolean;
  readonly dashedInferredEdges: boolean;
  /** `false` under cinema mode: a stray pointer must never enter a capture. */
  readonly interactive: boolean;
  readonly cinemaFrame: number | null;
  readonly onSample: (frameMs: number) => void;
}

export function WalkSceneContents({
  scene,
  palette,
  registry,
  runtime,
  labels,
  laneRails,
  dashedInferredEdges,
  interactive,
  cinemaFrame,
  onSample,
}: WalkSceneProps): JSX.Element {
  const objects = useMemo(
    () => createWalkObjects(scene, palette, { laneRails, dashedInferredEdges }),
    [scene, palette, laneRails, dashedInferredEdges],
  );

  useEffect(() => objects.dispose, [objects]);

  const onPointerMove = useCallback(
    (event: ThreeEvent<PointerEvent>) => {
      if (!interactive) return;
      const instanceId = event.instanceId ?? null;
      if (instanceId === runtime.hoverInstanceId) return;
      runtime.hoverInstanceId = instanceId;
      // `registry.mayAnimate` is consulted on EVERY write, not once at setup. The still
      // node is not in this mesh at all, so this is the second of two independent
      // refusals rather than the only one.
      writeHoverScale(objects, scene, instanceId, registry.mayAnimate);
    },
    [interactive, objects, registry, runtime, scene],
  );

  const onPointerOut = useCallback(() => {
    if (runtime.hoverInstanceId === null) return;
    runtime.hoverInstanceId = null;
    writeHoverScale(objects, scene, null, registry.mayAnimate);
  }, [objects, registry, runtime, scene]);

  return (
    <>
      <RailsRig runtime={runtime} cinemaFrame={cinemaFrame} onSample={onSample} />
      <LabelProjector labels={labels} runtime={runtime} />

      {objects.laneRails !== null && <primitive object={objects.laneRails} />}
      {objects.solidEdges !== null && <primitive object={objects.solidEdges} />}
      {objects.inferredEdges !== null && <primitive object={objects.inferredEdges} />}

      {objects.living !== null && (
        <primitive
          object={objects.living}
          onPointerMove={onPointerMove}
          onPointerOut={onPointerOut}
        />
      )}

      {objects.stillMeshes.map((mesh) => (
        <primitive key={mesh.name} object={mesh} />
      ))}
    </>
  );
}
