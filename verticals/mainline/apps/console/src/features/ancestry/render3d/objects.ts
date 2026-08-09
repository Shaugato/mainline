// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE SCENE, AS PLAIN three.js OBJECTS.
 *
 * No React in this file. `WalkScene.tsx` mounts what these factories build with
 * `<primitive>`, and `stillness.test.ts` / `projection.test.ts` construct the SAME
 * objects with no canvas, no GPU and no renderer — which is the only reason the
 * stillness rule can be asserted over the real scene graph in CI rather than over a
 * description of it.
 *
 * three.js needs a WebGL context to DRAW. It does not need one to build a geometry, a
 * material or a matrix, so every structural claim this surface makes is testable in
 * jsdom.
 *
 * ── THE FOUR MATERIALS, AND WHY NONE OF THEM CAN GLOW ────────────────────────────
 *
 * `MeshBasicMaterial`, `LineBasicMaterial` and `LineDashedMaterial` are all UNLIT. The
 * scene declares no light, so there is no emissive term, no specular highlight and no
 * shadow implying a light source anywhere in it. "Never emits" in the stillness rule is
 * therefore not a property the dead node has to defend — it is a property of the whole
 * scene, and the charter states it that way (§3, P6/S8).
 *
 * ── LIVING vs DEAD, AS GEOMETRY ──────────────────────────────────────────────────
 *
 * Living nodes are WIREFRAME boxes: open, provisional, still being written. The dead
 * node is a SOLID box: closed, dense, finished. That is the one piece of visual rhetoric
 * in this directory, it costs no colour and no shader, and it survives a monochrome
 * photocopy of a screenshot.
 */

import {
  BoxGeometry,
  BufferAttribute,
  BufferGeometry,
  Color,
  InstancedMesh,
  LineBasicMaterial,
  LineDashedMaterial,
  LineSegments,
  Matrix4,
  Mesh,
  MeshBasicMaterial,
  type Object3D,
} from 'three';

import type { PaletteHex } from './palette';
import { LIVING_NODE_SIZE, STILL_NODE_SIZE, type WalkNode, type WalkScene } from './projection';

/** Dash geometry for inferred edges. World units; deterministic, no time term. */
export const INFERRED_DASH_SIZE = 0.9;
export const INFERRED_GAP_SIZE = 0.7;

/** How far a hovered living node grows. Small on purpose: an acknowledgement, not an event. */
export const HOVER_SCALE = 1.45;

export interface WalkObjects {
  /** One draw call for every living node. `null` when there are none. */
  readonly living: InstancedMesh | null;
  /** `instanceId` → node id. The only way back from a raycast hit to a fact. */
  readonly instanceNodeIds: readonly string[];
  readonly solidEdges: LineSegments | null;
  readonly inferredEdges: LineSegments | null;
  /** One mesh per still node. Normally exactly one. Never instanced (charter §1, S7). */
  readonly stillMeshes: readonly Mesh[];
  readonly laneRails: LineSegments | null;
  /** Frees every geometry and material this factory allocated. */
  readonly dispose: () => void;
}

function colourOf(hex: string): Color {
  // setStyle() with the default sRGB colour space, matching the renderer's
  // outputColorSpace. The hex came from src/design/color.ts, which is the same
  // arithmetic the contrast gate uses, so the pixel and the audited value agree.
  return new Color().setStyle(hex);
}

/**
 * The living nodes, as one `InstancedMesh`.
 *
 * Every instance matrix is written ONCE, here, and `instanceMatrix.needsUpdate` is set
 * once. Nothing writes them per frame; the hover system writes exactly one matrix when
 * the pointer enters an instance and restores it when the pointer leaves, and it asks
 * the animation registry first.
 */
function createLivingNodes(
  nodes: readonly WalkNode[],
  palette: PaletteHex,
): { mesh: InstancedMesh | null; ids: readonly string[] } {
  if (nodes.length === 0) return { mesh: null, ids: [] };

  const geometry = new BoxGeometry(LIVING_NODE_SIZE, LIVING_NODE_SIZE, LIVING_NODE_SIZE);
  const material = new MeshBasicMaterial({
    color: colourOf(palette.living),
    wireframe: true,
    // The record that is still being written is drawn faintly. Not a fade-in: a constant.
    transparent: true,
    opacity: 0.72,
    toneMapped: false,
  });

  const mesh = new InstancedMesh(geometry, material, nodes.length);
  mesh.name = 'walk:living-nodes';
  const matrix = new Matrix4();
  const ids: string[] = [];
  nodes.forEach((node, index) => {
    matrix.makeTranslation(node.x, node.y, node.z);
    mesh.setMatrixAt(index, matrix);
    ids.push(node.id);
  });
  mesh.instanceMatrix.needsUpdate = true;
  return { mesh, ids };
}

function createEdgeGeometry(
  edges: readonly { readonly a: readonly [number, number, number]; readonly b: readonly [number, number, number] }[],
): BufferGeometry {
  const positions = new Float32Array(edges.length * 6);
  edges.forEach((edge, index) => {
    const offset = index * 6;
    positions[offset] = edge.a[0];
    positions[offset + 1] = edge.a[1];
    positions[offset + 2] = edge.a[2];
    positions[offset + 3] = edge.b[0];
    positions[offset + 4] = edge.b[1];
    positions[offset + 5] = edge.b[2];
  });
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(positions, 3));
  return geometry;
}

/**
 * Lane rails: one line per lane, running the whole depth of the walk.
 *
 * Derived entirely from the layout's own `lane` field and the nodes' own positions —
 * this adds no node and no edge, it adds a floor. It is the first thing the quality
 * ladder drops, because it is the only thing in the scene that carries no fact.
 */
function createLaneRails(scene: WalkScene, palette: PaletteHex): LineSegments | null {
  if (scene.nodes.length === 0) return null;

  const byLane = new Map<number, { xSum: number; yMin: number; count: number }>();
  for (const node of scene.nodes) {
    const existing = byLane.get(node.lane);
    if (existing === undefined) {
      byLane.set(node.lane, { xSum: node.x, yMin: node.y, count: 1 });
    } else {
      existing.xSum += node.x;
      existing.yMin = Math.min(existing.yMin, node.y);
      existing.count += 1;
    }
  }
  if (byLane.size === 0) return null;

  const segments: { a: readonly [number, number, number]; b: readonly [number, number, number] }[] =
    [];
  for (const [, lane] of [...byLane.entries()].sort((left, right) => left[0] - right[0])) {
    const x = lane.xSum / lane.count;
    const y = lane.yMin - LIVING_NODE_SIZE * 1.6;
    segments.push({ a: [x, y, 0], b: [x, y, scene.deepestZ] });
  }

  const material = new LineBasicMaterial({
    color: colourOf(palette.living),
    transparent: true,
    opacity: 0.16,
    toneMapped: false,
  });
  const rails = new LineSegments(createEdgeGeometry(segments), material);
  rails.name = 'walk:lane-rails';
  return rails;
}

/**
 * The still node.
 *
 * Everything about this function is the stillness rule:
 *
 *   • `matrixAutoUpdate = false` after ONE `updateMatrix()`, so no per-frame traversal
 *     recomputes it and `matrixWorld` is byte-identical after any number of advances.
 *   • `raycast` replaced with a function that records no intersection, so the pointer
 *     cannot reach it even if a future edit forgot to ask the animation registry.
 *   • its own `Mesh`, never an instance, so no shared buffer exists through which
 *     another node's animation could write to it.
 *   • `MeshBasicMaterial`, unlit, with no emissive and no transparency ramp.
 */
function createStillNode(node: WalkNode, palette: PaletteHex): Mesh {
  const geometry = new BoxGeometry(STILL_NODE_SIZE, STILL_NODE_SIZE, STILL_NODE_SIZE);
  const material = new MeshBasicMaterial({
    color: colourOf(palette.still),
    toneMapped: false,
  });
  const mesh = new Mesh(geometry, material);
  mesh.name = `walk:still:${node.id}`;
  mesh.position.set(node.x, node.y, node.z);
  mesh.updateMatrix();
  mesh.matrixAutoUpdate = false;
  mesh.matrixWorldNeedsUpdate = true;
  // Not hoverable. Not selectable. Not reachable by a pointer, by design and by physics.
  mesh.raycast = () => undefined;
  return mesh;
}

/** Builds every object in the scene. Pure apart from the allocations it returns. */
export function createWalkObjects(
  scene: WalkScene,
  palette: PaletteHex,
  options: { readonly laneRails: boolean; readonly dashedInferredEdges: boolean },
): WalkObjects {
  const { mesh: living, ids: instanceNodeIds } = createLivingNodes(scene.livingNodes, palette);

  const solid = scene.edges.filter(
    (edge) => !edge.inferred || !options.dashedInferredEdges,
  );
  const inferred = options.dashedInferredEdges
    ? scene.edges.filter((edge) => edge.inferred)
    : [];

  let solidEdges: LineSegments | null = null;
  if (solid.length > 0) {
    const material = new LineBasicMaterial({
      color: colourOf(palette.edge),
      toneMapped: false,
    });
    solidEdges = new LineSegments(createEdgeGeometry(solid), material);
    solidEdges.name = 'walk:edges-asserted';
  }

  let inferredEdges: LineSegments | null = null;
  if (inferred.length > 0) {
    const material = new LineDashedMaterial({
      color: colourOf(palette.edge),
      dashSize: INFERRED_DASH_SIZE,
      gapSize: INFERRED_GAP_SIZE,
      toneMapped: false,
    });
    inferredEdges = new LineSegments(createEdgeGeometry(inferred), material);
    // Required for LineDashedMaterial. Deterministic: the distances are a function of the
    // geometry, and the geometry is a function of the layout.
    inferredEdges.computeLineDistances();
    inferredEdges.name = 'walk:edges-inferred';
  }

  const stillMeshes = scene.stillNodes.map((node) => createStillNode(node, palette));
  const laneRails = options.laneRails ? createLaneRails(scene, palette) : null;

  const disposables: Object3D[] = [];
  if (living !== null) disposables.push(living);
  if (solidEdges !== null) disposables.push(solidEdges);
  if (inferredEdges !== null) disposables.push(inferredEdges);
  if (laneRails !== null) disposables.push(laneRails);
  disposables.push(...stillMeshes);

  return {
    living,
    instanceNodeIds,
    solidEdges,
    inferredEdges,
    stillMeshes,
    laneRails,
    dispose() {
      for (const object of disposables) {
        const holder = object as Object3D & {
          geometry?: { dispose: () => void };
          material?: { dispose: () => void };
        };
        holder.geometry?.dispose();
        holder.material?.dispose();
      }
      // InstancedMesh holds a per-instance buffer of its own.
      living?.dispose();
    },
  };
}

// ── The hover write, isolated so the rule guards exactly one function ────────────

const HOVER_MATRIX = new Matrix4();

/**
 * Scales one instance, or restores it.
 *
 * `mayAnimate` is the animation registry's runtime lock and is called on EVERY write,
 * not once at setup. That is the difference between a rule and a convention: even a
 * future edit that forgot to register its mutation cannot scale the dead.
 */
export function writeHoverScale(
  objects: WalkObjects,
  scene: WalkScene,
  instanceId: number | null,
  mayAnimate: (nodeId: string) => boolean,
): void {
  const mesh = objects.living;
  if (mesh === null) return;

  scene.livingNodes.forEach((node, index) => {
    const hovered = index === instanceId && mayAnimate(node.id);
    const size = hovered ? HOVER_SCALE : 1;
    HOVER_MATRIX.makeScale(size, size, size);
    HOVER_MATRIX.setPosition(node.x, node.y, node.z);
    mesh.setMatrixAt(index, HOVER_MATRIX);
  });
  mesh.instanceMatrix.needsUpdate = true;
}
