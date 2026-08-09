// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE STILLNESS RULE, AS ARITHMETIC.
 *
 *   > The severity-5 node is the only object in the scene that never moves, never
 *   > scales, never emits and never responds to hover. Everything else moves past it.
 *
 * `docs/leads/ui.md` §1.2.1 · D10 · `docs/dimensionality-charter.md` §1.
 *
 * ── PL-2: THIS SUITE WAS RED FIRST ───────────────────────────────────────────────
 *
 * For a product whose deliverable is a REFUSAL, a test that has never failed asserts
 * nothing. The deliberate-violation block below was run against a permissive
 * `assertAnimatable` (one whose still-node branch was commented out) and observed to
 * fail with:
 *
 *     × registering a tween against the severity-5 node throws
 *       → expected [Function] to throw an error
 *
 * before the refusal was restored. The two independent halves — the door
 * (`register()`) and the search (`stillnessViolations()`) — were each observed red on
 * their own, because a suite in which only one half can fail is a suite that would go
 * green the day somebody bypasses the other.
 */

import { describe, expect, it } from 'vitest';
import { InstancedMesh, Matrix4, Quaternion, Raycaster, Vector3 } from 'three';

import {
  buildSceneRegistry,
  createAnimationRegistry,
} from '../../../src/features/ancestry/render3d/animation-registry';
import { createWalkObjects, writeHoverScale } from '../../../src/features/ancestry/render3d/objects';
import { resolvePalette } from '../../../src/features/ancestry/render3d/palette';
import { projectWalk } from '../../../src/features/ancestry/render3d/projection';
import {
  FATALITY_SEVERITY,
  isStillNode,
  isStillSeverity,
  StillnessViolationError,
  stillnessViolations,
  type MutationEntry,
} from '../../../src/features/ancestry/render3d/stillness';
import { FIXTURE_LAYOUT, STILL_NODE_ID, layoutWithoutFatality } from './_fixture';

const PALETTE = resolvePalette();
const SCENE = projectWalk(FIXTURE_LAYOUT);
const severityOf = (id: string): number | undefined =>
  SCENE.nodes.find((node) => node.id === id)?.severity;

describe('the predicate', () => {
  it('confers stillness on severity 5 and on nothing else', () => {
    expect(FATALITY_SEVERITY).toBe(5);
    for (const severity of [0, 1, 2, 3, 4]) {
      expect(isStillSeverity(severity)).toBe(false);
    }
    expect(isStillSeverity(5)).toBe(true);
  });

  it('is exact rather than a threshold, so an out-of-contract 6 is not silently a fatality', () => {
    // contracts/common.schema.json caps severity at 5. A `>= 5` predicate would accept a
    // 6 and treat it as a fatality without anybody deciding that.
    expect(isStillSeverity(6)).toBe(false);
  });

  it('does not read virulence — a routine commit inside a fatal closure is not the dead node', () => {
    const commit = FIXTURE_LAYOUT.nodes.find((node) => node.id === 'cm-2003-origin');
    expect(commit?.virulence).toBe('blood_fatal');
    expect(isStillNode({ id: 'cm-2003-origin', severity: commit?.severity ?? -1 })).toBe(false);
  });
});

describe('the projection writes the flag; nobody supplies it', () => {
  it('marks exactly the severity-5 node still', () => {
    expect(SCENE.stillNodes.map((node) => node.id)).toEqual([STILL_NODE_ID]);
    expect(SCENE.livingNodes.some((node) => node.severity === 5)).toBe(false);
    expect(SCENE.livingNodes).toHaveLength(FIXTURE_LAYOUT.nodes.length - 1);
  });

  it('marks nothing still when the ancestry contains no fatality', () => {
    const scene = projectWalk(layoutWithoutFatality());
    expect(scene.stillNodes).toHaveLength(0);
    expect(scene.livingNodes).toHaveLength(FIXTURE_LAYOUT.nodes.length);
  });
});

describe('the deliberate violation', () => {
  it('registering a tween against the severity-5 node throws', () => {
    const registry = createAnimationRegistry(SCENE.nodes);
    expect(() => {
      registry.register('hover-scale', STILL_NODE_ID, 'a test that should not be allowed to pass');
    }).toThrow(StillnessViolationError);
  });

  it('names the node, the mutation and the source in the failure', () => {
    const registry = createAnimationRegistry(SCENE.nodes);
    try {
      registry.register('pointer-proximity', STILL_NODE_ID, 'deliberate violation');
      expect.unreachable('the registry accepted a mutation against the severity-5 node');
    } catch (error) {
      expect(error).toBeInstanceOf(StillnessViolationError);
      const violation = error as StillnessViolationError;
      expect(violation.nodeId).toBe(STILL_NODE_ID);
      expect(violation.mutationKind).toBe('pointer-proximity');
      expect(violation.message).toContain('deliberate violation');
      expect(violation.message).toContain('THE STILLNESS RULE');
    }
  });

  it('refuses every mutation kind, not just the obvious one', () => {
    const kinds: MutationEntry['kind'][] = [
      'hover-scale',
      'pointer-proximity',
      'rail-travel',
      'label-fade',
      'edge-dash-offset',
      'instance-matrix',
    ];
    for (const kind of kinds) {
      const registry = createAnimationRegistry(SCENE.nodes);
      expect(() => {
        registry.register(kind, STILL_NODE_ID, `deliberate ${kind}`);
      }).toThrow(StillnessViolationError);
    }
  });

  it('a registry assembled by BYPASSING register() is still caught by the audit', () => {
    // The door can be walked around: an entry array can be built by hand. The audit is
    // the search, and this is the case it exists for.
    const smuggled: MutationEntry[] = [
      { kind: 'rail-travel', targetNodeId: null, source: 'the camera' },
      { kind: 'hover-scale', targetNodeId: 'cm-2019-reflow', source: 'a living node' },
      { kind: 'instance-matrix', targetNodeId: STILL_NODE_ID, source: 'smuggled past the door' },
    ];
    const found = stillnessViolations(smuggled, severityOf);
    expect(found).toHaveLength(1);
    expect(found[0]?.nodeId).toBe(STILL_NODE_ID);
    expect(found[0]?.source).toBe('smuggled past the door');
  });

  it('refuses a mutation whose target is not in the scene at all', () => {
    const registry = createAnimationRegistry(SCENE.nodes);
    expect(() => {
      registry.register('hover-scale', 'no-such-node', 'a typo');
    }).toThrow(/not in the scene/);
  });
});

describe('the registry the shipped scene actually builds', () => {
  const registry = buildSceneRegistry(SCENE.nodes);

  it('reports no violations', () => {
    expect(registry.violations()).toEqual([]);
  });

  it('registers no entry whose target is the severity-5 node', () => {
    const targets = registry.entries().map((entry) => entry.targetNodeId);
    expect(targets).not.toContain(STILL_NODE_ID);
  });

  it('registers a hover mutation for every living node and for no other node', () => {
    const hovered = registry
      .entries()
      .filter((entry) => entry.kind === 'hover-scale')
      .map((entry) => entry.targetNodeId);
    expect(hovered.slice().sort()).toEqual(SCENE.livingNodes.map((node) => node.id).sort());
  });

  it('refuses the still node at the runtime lock as well as at the door', () => {
    expect(registry.mayAnimate(STILL_NODE_ID)).toBe(false);
    expect(registry.mayAnimate('cm-2019-reflow')).toBe(true);
    // An unknown node is refused too: "cannot be shown to be safe" resolves to no.
    expect(registry.mayAnimate('no-such-node')).toBe(false);
  });

  it('knows which ids are still without the caller re-deriving the rule', () => {
    expect(registry.stillNodeIds()).toEqual([STILL_NODE_ID]);
  });

  it('registers the camera against no node — the scene stands still, the observer moves', () => {
    const rail = registry.entries().find((entry) => entry.kind === 'rail-travel');
    expect(rail?.targetNodeId).toBeNull();
  });
});

describe('the still node, as a three.js object', () => {
  const objects = createWalkObjects(SCENE, PALETTE, {
    laneRails: true,
    dashedInferredEdges: true,
  });

  it('is its own mesh and never an instance of the living-node batch', () => {
    expect(objects.stillMeshes).toHaveLength(1);
    expect(objects.instanceNodeIds).not.toContain(STILL_NODE_ID);
    expect(objects.living).toBeInstanceOf(InstancedMesh);
    expect(objects.living?.count).toBe(SCENE.livingNodes.length);
  });

  it('has matrixAutoUpdate off, so no traversal recomputes its position', () => {
    const mesh = objects.stillMeshes[0];
    expect(mesh?.matrixAutoUpdate).toBe(false);
  });

  it('has a byte-identical world matrix after any number of advanced frames', () => {
    const mesh = objects.stillMeshes[0];
    if (mesh === undefined) throw new Error('no still mesh');
    mesh.updateMatrixWorld(true);
    const before = new Matrix4().copy(mesh.matrixWorld).elements.slice();
    for (let frame = 0; frame < 240; frame += 1) {
      mesh.updateMatrixWorld(true);
    }
    expect(Array.from(mesh.matrixWorld.elements)).toEqual(Array.from(before));
  });

  it('records no intersection, so a pointer cannot reach it', () => {
    const mesh = objects.stillMeshes[0];
    if (mesh === undefined) throw new Error('no still mesh');
    const raycaster = new Raycaster(new Vector3(0, 0, 10), new Vector3(0, 0, -1));
    const intersects: unknown[] = [];
    mesh.raycast(raycaster, intersects as never);
    expect(intersects).toHaveLength(0);
  });

  it('has no emissive term — the material is unlit and the scene declares no light', () => {
    const mesh = objects.stillMeshes[0];
    const material = mesh?.material as { emissive?: unknown; type?: string } | undefined;
    expect(material?.type).toBe('MeshBasicMaterial');
    expect(material?.emissive).toBeUndefined();
  });

  it('cannot be scaled by the hover writer, because it is not in the instance list', () => {
    const registry = buildSceneRegistry(SCENE.nodes);
    const mesh = objects.living;
    if (mesh === null) throw new Error('no instanced mesh');

    const stillBefore = new Matrix4().copy(objects.stillMeshes[0]?.matrix ?? new Matrix4());
    // Hover every instance in turn, including an out-of-range id.
    for (let instanceId = -1; instanceId <= SCENE.livingNodes.length; instanceId += 1) {
      writeHoverScale(objects, SCENE, instanceId, registry.mayAnimate);
    }
    const stillAfter = objects.stillMeshes[0]?.matrix ?? new Matrix4();
    expect(Array.from(stillAfter.elements)).toEqual(Array.from(stillBefore.elements));

    // And every living instance is back at scale 1 once the pointer leaves.
    writeHoverScale(objects, SCENE, null, registry.mayAnimate);
    const read = new Matrix4();
    for (let index = 0; index < SCENE.livingNodes.length; index += 1) {
      mesh.getMatrixAt(index, read);
      const scale = new Vector3();
      read.decompose(new Vector3(), new Quaternion(), scale);
      expect(scale.x).toBeCloseTo(1, 6);
    }
  });

  it('scales a living instance when hovered — everything else moves past the dead', () => {
    const registry = buildSceneRegistry(SCENE.nodes);
    const mesh = objects.living;
    if (mesh === null) throw new Error('no instanced mesh');
    writeHoverScale(objects, SCENE, 0, registry.mayAnimate);
    const read = new Matrix4();
    mesh.getMatrixAt(0, read);
    const scale = new Vector3();
    read.decompose(new Vector3(), new Quaternion(), scale);
    expect(scale.x).toBeGreaterThan(1);
  });
});
