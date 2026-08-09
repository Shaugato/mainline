// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE PROJECTION — `AncestryLayout` → `WalkScene`.
 *
 * One pure function, no clock, no randomness, no I/O, no React. It is the only place in
 * this directory where a coordinate is computed, and it is deliberately the boringest
 * file here, because the interesting property is what it DOESN'T do:
 *
 *   > Consume the AncestryLayout unchanged. You may add a z projection from the existing
 *   > t field, and you may NOT compute a different graph, add a node, or drop one.
 *
 * So: the node list is walked once, in order, and every input node becomes exactly one
 * output node with the same id. The edge list is walked once, in order, and every input
 * edge becomes exactly one output edge. `assertLayoutParity()` re-checks that afterwards
 * over the produced scene, and `projection.test.ts` runs the check on every fixture.
 *
 * ── WHAT IS ADDED ────────────────────────────────────────────────────────────────
 *
 *   z      derived from `t` against `timeExtent`. THE THIRD AXIS IS TIME. Present at
 *          z = 0, the oldest ancestor at z = −SCENE_DEPTH.
 *   x, y   one affine transform — centre and uniform scale — derived from the layout's
 *          own extents so the walk fits a fixed frustum. Affine and uniform means the
 *          shape a reader sees is the shape the ribbon prints; a per-axis scale would
 *          make the two renderers disagree about an angle.
 *   still  derived from `severity`. See `stillness.ts`. Projected, never supplied.
 *
 * ── WHAT IS REFUSED ──────────────────────────────────────────────────────────────
 *
 * A layout with a person-shaped field on a node (D15 / I15 / §11.5's Attribution Rule).
 * A node whose `t` falls outside the declared `timeExtent`. An edge naming a node that
 * is not in the layout. A non-finite coordinate. Each of those is a breach one hop
 * upstream, and each throws with the sentence naming the breach — P3, fail closed on
 * missing or incoherent evidence, and never draw something that cannot be shown to be
 * what it claims to be.
 */

import {
  isAncestryLayout,
  type AncestryLayout,
  type LayoutNodeKind,
  type VirulenceClass,
} from './contract';
import { isStillSeverity } from './stillness';

// ── The frustum this scene is built for ──────────────────────────────────────────
//
// World units. They are arbitrary in the way a page size is arbitrary: what matters is
// that every module agrees, that the camera's standoff is expressible in them, and that
// the numbers are in one file so a reader can see the whole scene's scale at once.

/** How far back the walk reaches, in world units. The whole time extent maps onto this. */
export const SCENE_DEPTH = 120;

/** Half-width and half-height of the frustum the layout is fitted into. */
export const SCENE_HALF_WIDTH = 17;
export const SCENE_HALF_HEIGHT = 9;

/**
 * A ceiling on the affine scale.
 *
 * A three-node ancestry has a tiny `(x, y)` extent, and fitting it to the frustum would
 * magnify it until three commits filled the screen like a logo. The cap makes a small
 * walk LOOK small, which is true and is the point.
 */
export const MAX_XY_SCALE = 0.12;

/** Edge length of a living node's cube. Living nodes are small; the dead node is not. */
export const LIVING_NODE_SIZE = 0.85;

/** Edge length of the still node. Larger, and it is the only object with its own mesh. */
export const STILL_NODE_SIZE = 2.6;

// ── The projected scene ──────────────────────────────────────────────────────────

export interface WalkNode {
  readonly id: string;
  readonly kind: LayoutNodeKind;
  readonly severity: number;
  readonly virulence: VirulenceClass;
  readonly lane: number;
  readonly label: string;
  /** The layout's own time coordinate, carried through untouched. */
  readonly t: number;
  readonly x: number;
  readonly y: number;
  /** Derived from `t`. Negative is older. */
  readonly z: number;
  /**
   * THE STILLNESS FLAG. Derived from `severity` by this function and by nothing else.
   * There is no constructor for `WalkNode` outside this module, so there is no path by
   * which a renderer supplies its own answer (P2).
   */
  readonly still: boolean;
}

export interface WalkEdge {
  readonly from: string;
  readonly to: string;
  /** The layout's `mainline.blame_basis` value, carried through untouched. */
  readonly basis: string;
  readonly inferred: boolean;
  readonly a: readonly [number, number, number];
  readonly b: readonly [number, number, number];
}

/** How the `t` axis should be spoken to a reader. See `interpretTimeAxis`. */
export type TimeUnit = 'epoch_ms' | 'epoch_s' | 'abstract';

export interface WalkScene {
  readonly nodes: readonly WalkNode[];
  readonly edges: readonly WalkEdge[];
  /** Every node that is still. Normally exactly one; the type does not assume it. */
  readonly stillNodes: readonly WalkNode[];
  /** Nodes that are not still, in layout order. These are the instanced mesh's instances. */
  readonly livingNodes: readonly WalkNode[];
  readonly timeExtent: readonly [number, number];
  readonly timeUnit: TimeUnit;
  readonly lanes: number;
  readonly truncated: boolean;
  readonly ancestryComplete: boolean;
  readonly closureGen: number;
  /** The z of the oldest node in the scene — where the rail ends. */
  readonly deepestZ: number;
}

// ── The attribution refusal ──────────────────────────────────────────────────────

/**
 * Key fragments that would mean a person had reached this renderer.
 *
 * Matched case-insensitively against a node's OWN keys. This is a deliberately blunt
 * instrument: a false positive is a five-minute conversation about a field name, and a
 * false negative is a person's name rendered into a screenshot that outlives the schema.
 *
 * `name` is on the list and `label` is not, and that distinction is the contract:
 * `contracts/ancestry.schema.json` says an event title "names a failure, never a person",
 * so `label` is the sanctioned prose field and `name` is not a field this payload has.
 */
const PERSON_KEY_FRAGMENTS: readonly string[] = [
  'signer',
  'sub',
  'person',
  'name',
  'actor',
  'user',
  'author',
  'operator',
  'supervisor',
  'employee',
  'email',
  'who',
];

/**
 * Refuses a layout whose nodes carry a person-shaped field.
 *
 * It throws rather than filtering. A renderer that quietly dropped the field would hide
 * a schema breach that `ARCHITECTURE.md` §11.5 and I15 exist to prevent, and the whole
 * value of D15 is that the refusal is visible at the boundary where a screenshot would
 * otherwise have been taken.
 */
export function assertNoPersonFields(layout: AncestryLayout): void {
  for (const node of layout.nodes) {
    for (const key of Object.keys(node)) {
      const lowered = key.toLowerCase();
      const hit = PERSON_KEY_FRAGMENTS.find((fragment) => lowered.includes(fragment));
      if (hit !== undefined) {
        throw new Error(
          `THE ATTRIBUTION RULE (D15 / I15 / ARCHITECTURE.md §11.5): the ancestry layout gave the ` +
            `MEMORY register a node (${node.id}) carrying the field "${key}", which matches the ` +
            `person vocabulary fragment "${hit}". No named person is rendered in the MEMORY ` +
            `register, ever. This is refused at the renderer rather than filtered, because a ` +
            `payload that carries a person is a breach one hop upstream and dropping the field ` +
            `here would hide it.`,
        );
      }
    }
  }
}

// ── The time axis ────────────────────────────────────────────────────────────────

/** 1973-03-03 in ms — below this, an epoch-ms value is implausible for a mining corpus. */
const EPOCH_MS_FLOOR = 1e11;
/** 1973-03-03 in s. Above `EPOCH_MS_FLOOR / 1000`. */
const EPOCH_S_FLOOR = 1e8;

/**
 * What `t` MEANS, decided from its magnitude and stated rather than assumed.
 *
 * The layout contract says `t` is "the time coordinate" and does not fix a unit. This
 * surface needs to know, because it prints years on the rail, and printing "1970" over a
 * 2013 fatality because the axis was in seconds would be a fabricated claim about when
 * somebody died.
 *
 * So the unit is INFERRED and the inference is conservative: anything that is not
 * confidently an epoch is `abstract`, and an `abstract` axis gets no year labels at all —
 * only a relative depth. A missing label is a gap; a wrong one is a lie.
 */
export function interpretTimeAxis(timeExtent: readonly [number, number]): TimeUnit {
  const [lo, hi] = timeExtent;
  const magnitude = Math.max(Math.abs(lo), Math.abs(hi));
  if (magnitude >= EPOCH_MS_FLOOR) return 'epoch_ms';
  if (magnitude >= EPOCH_S_FLOOR) return 'epoch_s';
  return 'abstract';
}

/** The UTC year for a `t`, or `null` when the axis carries no calendar meaning. */
export function yearAt(t: number, unit: TimeUnit): number | null {
  if (unit === 'abstract') return null;
  const ms = unit === 'epoch_ms' ? t : t * 1000;
  if (!Number.isFinite(ms)) return null;
  // Explicit UTC. An evidentiary instant is UTC everywhere in this console; a year that
  // shifts with the reader's timezone is a different year in December.
  return new Date(ms).getUTCFullYear();
}

// ── The projection ───────────────────────────────────────────────────────────────

function refuse(message: string): never {
  throw new Error(`render3d/projection: ${message}`);
}

/**
 * Projects a layout into a scene.
 *
 * Pure. Deterministic. Called with the same layout twice, it returns two structurally
 * identical scenes — `projection.test.ts` asserts that over 100 runs, the same way the
 * layout engine's own determinism is asserted.
 */
export function projectWalk(layout: AncestryLayout): WalkScene {
  if (!isAncestryLayout(layout)) {
    refuse(
      'the value handed to the walk is not an AncestryLayout. The walk renders the layout the ' +
        'ribbon renders and computes no graph of its own; if there is no layout there is nothing ' +
        'to draw, and the ribbon carries every fact regardless (ui.md §1.3).',
    );
  }

  assertNoPersonFields(layout);

  const [tLo, tHi] = layout.timeExtent;
  if (tHi < tLo) {
    refuse(`timeExtent is inverted: [${tLo}, ${tHi}]. The rail cannot run backwards.`);
  }
  const span = tHi - tLo;

  // ── (x, y): one centre, one uniform scale, both from the layout's own extents ──
  let xMin = Number.POSITIVE_INFINITY;
  let xMax = Number.NEGATIVE_INFINITY;
  let yMin = Number.POSITIVE_INFINITY;
  let yMax = Number.NEGATIVE_INFINITY;
  for (const node of layout.nodes) {
    if (node.t < tLo || node.t > tHi) {
      refuse(
        `node ${node.id} has t=${node.t}, outside the declared timeExtent [${tLo}, ${tHi}]. ` +
          `A node at an undefined depth is a silent claim about when something happened.`,
      );
    }
    if (node.x < xMin) xMin = node.x;
    if (node.x > xMax) xMax = node.x;
    if (node.y < yMin) yMin = node.y;
    if (node.y > yMax) yMax = node.y;
  }

  const hasNodes = layout.nodes.length > 0;
  const xMid = hasNodes ? (xMin + xMax) / 2 : 0;
  const yMid = hasNodes ? (yMin + yMax) / 2 : 0;
  const xHalf = hasNodes ? (xMax - xMin) / 2 : 0;
  const yHalf = hasNodes ? (yMax - yMin) / 2 : 0;

  const xScale = xHalf > 0 ? SCENE_HALF_WIDTH / xHalf : MAX_XY_SCALE;
  const yScale = yHalf > 0 ? SCENE_HALF_HEIGHT / yHalf : MAX_XY_SCALE;
  const scale = Math.min(xScale, yScale, MAX_XY_SCALE);

  const timeUnit = interpretTimeAxis(layout.timeExtent);

  const nodes: WalkNode[] = [];
  const positionById = new Map<string, readonly [number, number, number]>();

  for (const node of layout.nodes) {
    // Present at 0, oldest at −SCENE_DEPTH. A degenerate extent (one instant) collapses
    // to a single plane rather than dividing by zero — one instant HAS no depth.
    const z = span > 0 ? -((tHi - node.t) / span) * SCENE_DEPTH : 0;
    const x = (node.x - xMid) * scale;
    // The layout is an SVG-space layout: y grows DOWNWARD. World space grows upward.
    const y = -(node.y - yMid) * scale;

    if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) {
      refuse(`node ${node.id} projected to a non-finite position (${x}, ${y}, ${z}).`);
    }
    if (positionById.has(node.id)) {
      refuse(
        `node id ${node.id} appears twice in the layout. The walk draws the layout it is given ` +
          `and does not de-duplicate: a duplicate id means two different facts share one identity.`,
      );
    }

    const walkNode: WalkNode = {
      id: node.id,
      kind: node.kind,
      severity: node.severity,
      virulence: node.virulence,
      lane: node.lane,
      label: node.label,
      t: node.t,
      x,
      y,
      z,
      still: isStillSeverity(node.severity),
    };
    nodes.push(walkNode);
    positionById.set(node.id, [x, y, z]);
  }

  const edges: WalkEdge[] = [];
  for (const edge of layout.edges) {
    const a = positionById.get(edge.from);
    const b = positionById.get(edge.to);
    if (a === undefined || b === undefined) {
      refuse(
        `edge ${edge.from} → ${edge.to} names a node the layout does not contain. An edge to ` +
          `nowhere cannot be drawn honestly, and dropping it would silently shrink the ancestry.`,
      );
    }
    edges.push({
      from: edge.from,
      to: edge.to,
      basis: edge.basis,
      inferred: edge.inferred,
      a,
      b,
    });
  }

  const stillNodes = nodes.filter((node) => node.still);
  const livingNodes = nodes.filter((node) => !node.still);
  const deepestZ = nodes.reduce((lowest, node) => Math.min(lowest, node.z), 0);

  return Object.freeze({
    nodes: Object.freeze(nodes),
    edges: Object.freeze(edges),
    stillNodes: Object.freeze(stillNodes),
    livingNodes: Object.freeze(livingNodes),
    timeExtent: layout.timeExtent,
    timeUnit,
    lanes: layout.lanes,
    truncated: layout.truncated,
    ancestryComplete: layout.ancestryComplete,
    closureGen: layout.closureGen,
    deepestZ,
  });
}

// ── Parity ───────────────────────────────────────────────────────────────────────

/**
 * The machine-readable description of what the scene contains.
 *
 * This is what the browser spec reads off the DOM (`data-walk-node-ids`) and compares
 * with the ribbon, and what `projection.test.ts` compares with the layout. It exists as
 * a value rather than as a walk over `THREE.Scene.children` on purpose: a scene-graph
 * assertion that needs a GPU is an assertion that does not run in CI.
 */
export interface SceneGraphManifest {
  readonly nodeIds: readonly string[];
  /** `from→to` per edge, in layout order, duplicates preserved. */
  readonly edgeKeys: readonly string[];
  readonly stillNodeIds: readonly string[];
  /** Always 0. A scene with no light cannot glow (charter §3, S8). */
  readonly lightCount: 0;
  /**
   * How many draw calls the bulk geometry costs, independent of node count:
   * one InstancedMesh + one solid LineSegments + one dashed LineSegments + one mesh per
   * still node.
   */
  readonly bulkDrawCalls: number;
}

export function edgeKey(edge: { readonly from: string; readonly to: string }): string {
  return `${edge.from}→${edge.to}`;
}

export function sceneGraphOf(scene: WalkScene): SceneGraphManifest {
  return Object.freeze({
    nodeIds: Object.freeze(scene.nodes.map((node) => node.id)),
    edgeKeys: Object.freeze(scene.edges.map(edgeKey)),
    stillNodeIds: Object.freeze(scene.stillNodes.map((node) => node.id)),
    lightCount: 0,
    bulkDrawCalls:
      (scene.livingNodes.length > 0 ? 1 : 0) +
      (scene.edges.some((edge) => !edge.inferred) ? 1 : 0) +
      (scene.edges.some((edge) => edge.inferred) ? 1 : 0) +
      scene.stillNodes.length,
  });
}

/**
 * Asserts the scene is the layout — no node added, none dropped, none re-ordered, and
 * the same for edges. Returns the differences rather than throwing, so a test can print
 * all of them at once.
 */
export function layoutParityDifferences(
  layout: AncestryLayout,
  scene: WalkScene,
): readonly string[] {
  const problems: string[] = [];
  const layoutNodeIds = layout.nodes.map((node) => node.id);
  const sceneNodeIds = scene.nodes.map((node) => node.id);
  if (layoutNodeIds.length !== sceneNodeIds.length) {
    problems.push(
      `node count: layout has ${layoutNodeIds.length}, scene has ${sceneNodeIds.length}.`,
    );
  }
  for (let i = 0; i < Math.max(layoutNodeIds.length, sceneNodeIds.length); i += 1) {
    const expected = layoutNodeIds[i];
    const actual = sceneNodeIds[i];
    if (expected !== actual) {
      problems.push(`node[${i}]: layout ${String(expected)} ≠ scene ${String(actual)}.`);
    }
  }
  const layoutEdgeKeys = layout.edges.map(edgeKey);
  const sceneEdgeKeys = scene.edges.map(edgeKey);
  if (layoutEdgeKeys.length !== sceneEdgeKeys.length) {
    problems.push(
      `edge count: layout has ${layoutEdgeKeys.length}, scene has ${sceneEdgeKeys.length}.`,
    );
  }
  for (let i = 0; i < Math.max(layoutEdgeKeys.length, sceneEdgeKeys.length); i += 1) {
    const expected = layoutEdgeKeys[i];
    const actual = sceneEdgeKeys[i];
    if (expected !== actual) {
      problems.push(`edge[${i}]: layout ${String(expected)} ≠ scene ${String(actual)}.`);
    }
  }
  return problems;
}
