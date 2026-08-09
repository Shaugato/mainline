// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE PARITY GATE — the walk adds no fact and drops none.
 *
 * `docs/leads/ui.md` D11 / §1.3: one layout, two renderers, with a test asserting the
 * 3D scene ⊆ the ribbon. This file asserts the stronger form, which is what the brief
 * actually requires of this worker:
 *
 *   > Consume the AncestryLayout produced by W6's worker unchanged. You may add a z
 *   > projection from the existing t field, and you may NOT compute a different graph,
 *   > add a node, or drop one.
 *
 * 3D ≡ LAYOUT, node for node and edge for edge, in order. Since the ribbon renders the
 * same layout, 3D ⊆ ribbon follows — and it follows without this suite needing to know
 * anything about the ribbon's DOM, which is what keeps two workers' tests from having
 * to agree on a selector before either can be green.
 */

import { describe, expect, it } from 'vitest';

import {
  SCENE_DEPTH,
  SCENE_HALF_HEIGHT,
  SCENE_HALF_WIDTH,
  interpretTimeAxis,
  layoutParityDifferences,
  projectWalk,
  sceneGraphOf,
  yearAt,
} from '../../../src/features/ancestry/render3d/projection';
import type { AncestryLayout } from '../../../src/features/ancestry/render3d/contract';
import { FIXTURE_LAYOUT, layoutWithAbstractTime } from './_fixture';

const SCENE = projectWalk(FIXTURE_LAYOUT);

describe('the graph is the layout, unchanged', () => {
  it('reports no parity differences at all', () => {
    expect(layoutParityDifferences(FIXTURE_LAYOUT, SCENE)).toEqual([]);
  });

  it('emits exactly one scene node per layout node, in layout order', () => {
    expect(SCENE.nodes.map((node) => node.id)).toEqual(FIXTURE_LAYOUT.nodes.map((node) => node.id));
  });

  it('emits exactly one scene edge per layout edge, in layout order', () => {
    expect(SCENE.edges.map((edge) => `${edge.from}→${edge.to}`)).toEqual(
      FIXTURE_LAYOUT.edges.map((edge) => `${edge.from}→${edge.to}`),
    );
  });

  it('carries every edge basis through untouched — an inferred link stays inferred', () => {
    expect(SCENE.edges.map((edge) => edge.basis)).toEqual(
      FIXTURE_LAYOUT.edges.map((edge) => edge.basis),
    );
    expect(SCENE.edges.filter((edge) => edge.inferred)).toHaveLength(
      FIXTURE_LAYOUT.edges.filter((edge) => edge.inferred).length,
    );
  });

  it('carries lane, severity, virulence, label and t through without re-deriving any of them', () => {
    for (const source of FIXTURE_LAYOUT.nodes) {
      const projected = SCENE.nodes.find((node) => node.id === source.id);
      expect(projected).toBeDefined();
      expect(projected?.lane).toBe(source.lane);
      expect(projected?.severity).toBe(source.severity);
      expect(projected?.virulence).toBe(source.virulence);
      expect(projected?.label).toBe(source.label);
      expect(projected?.t).toBe(source.t);
      expect(projected?.kind).toBe(source.kind);
    }
  });

  it('splits the nodes into still and living without losing one', () => {
    expect(SCENE.stillNodes.length + SCENE.livingNodes.length).toBe(FIXTURE_LAYOUT.nodes.length);
  });

  it('detects a difference when one is planted — the gate is capable of failing', () => {
    const tampered = { ...SCENE, nodes: SCENE.nodes.slice(1) };
    expect(layoutParityDifferences(FIXTURE_LAYOUT, tampered)).not.toEqual([]);
  });
});

describe('determinism', () => {
  it('produces a structurally identical scene on every run', () => {
    const first = projectWalk(FIXTURE_LAYOUT);
    for (let run = 0; run < 100; run += 1) {
      expect(projectWalk(FIXTURE_LAYOUT)).toEqual(first);
    }
  });

  it('draws no random number and reads no clock — the same bytes give the same scene', () => {
    // Asserted structurally in rails.test.ts's source scan; here it is asserted
    // behaviourally, by pinning Date.now to something absurd and re-projecting.
    const before = projectWalk(FIXTURE_LAYOUT);
    const realNow = Date.now;
    try {
      Date.now = () => 0;
      expect(projectWalk(FIXTURE_LAYOUT)).toEqual(before);
    } finally {
      Date.now = realNow;
    }
  });
});

describe('the third axis is time', () => {
  it('puts the newest node at z = 0 and the oldest at −SCENE_DEPTH', () => {
    const zs = SCENE.nodes.map((node) => node.z);
    expect(Math.max(...zs)).toBeCloseTo(0, 9);
    expect(Math.min(...zs)).toBeCloseTo(-SCENE_DEPTH, 9);
    expect(SCENE.deepestZ).toBeCloseTo(-SCENE_DEPTH, 9);
  });

  it('is monotone: an older node is never nearer the camera than a younger one', () => {
    const ordered = SCENE.nodes.slice().sort((left, right) => left.t - right.t);
    for (let index = 1; index < ordered.length; index += 1) {
      const previous = ordered[index - 1];
      const current = ordered[index];
      if (previous === undefined || current === undefined) continue;
      expect(current.z).toBeGreaterThanOrEqual(previous.z - 1e-9);
    }
  });

  it('collapses to a single plane when the whole ancestry is one instant', () => {
    const instant = FIXTURE_NODES_AT_ONE_INSTANT();
    const scene = projectWalk(instant);
    expect(scene.nodes.every((node) => node.z === 0)).toBe(true);
    expect(scene.deepestZ).toBe(0);
  });
});

describe('the (x, y) transform is affine and uniform', () => {
  it('preserves the aspect of every pair — one scale, not one per axis', () => {
    const pairs: number[] = [];
    for (let i = 0; i < FIXTURE_LAYOUT.nodes.length - 1; i += 1) {
      const a = FIXTURE_LAYOUT.nodes[i];
      const b = FIXTURE_LAYOUT.nodes[i + 1];
      const pa = SCENE.nodes[i];
      const pb = SCENE.nodes[i + 1];
      if (a === undefined || b === undefined || pa === undefined || pb === undefined) continue;
      const layoutDistance = Math.hypot(a.x - b.x, a.y - b.y);
      const sceneDistance = Math.hypot(pa.x - pb.x, pa.y - pb.y);
      if (layoutDistance === 0) continue;
      pairs.push(sceneDistance / layoutDistance);
    }
    expect(pairs.length).toBeGreaterThan(3);
    for (const ratio of pairs) {
      expect(ratio).toBeCloseTo(pairs[0] ?? 0, 9);
    }
  });

  it('keeps the walk inside the frustum box', () => {
    for (const node of SCENE.nodes) {
      expect(Math.abs(node.x)).toBeLessThanOrEqual(SCENE_HALF_WIDTH + 1e-9);
      expect(Math.abs(node.y)).toBeLessThanOrEqual(SCENE_HALF_HEIGHT + 1e-9);
    }
  });

  it('flips y, because the layout is SVG space and the scene is world space', () => {
    const lowestInLayout = FIXTURE_LAYOUT.nodes.reduce((best, node) =>
      node.y > best.y ? node : best,
    );
    const projected = SCENE.nodes.find((node) => node.id === lowestInLayout.id);
    const others = SCENE.nodes.filter((node) => node.id !== lowestInLayout.id);
    expect(projected).toBeDefined();
    for (const other of others) {
      expect(projected?.y ?? 0).toBeLessThanOrEqual(other.y + 1e-9);
    }
  });
});

describe('the refusals', () => {
  it('refuses a value that is not a layout at all', () => {
    expect(() => projectWalk({} as unknown as AncestryLayout)).toThrow(/not an AncestryLayout/);
  });

  it('refuses a node whose t falls outside the declared timeExtent', () => {
    const broken: AncestryLayout = {
      ...FIXTURE_LAYOUT,
      nodes: FIXTURE_LAYOUT.nodes.map((node, index) =>
        index === 0 ? { ...node, t: node.t - 1_000_000 } : node,
      ),
    };
    expect(() => projectWalk(broken)).toThrow(/outside the declared timeExtent/);
  });

  it('refuses an edge naming a node the layout does not contain', () => {
    const broken: AncestryLayout = {
      ...FIXTURE_LAYOUT,
      edges: [...FIXTURE_LAYOUT.edges, { from: 'ghost', to: 'cm-2003-origin', basis: 'asserted_human', inferred: false }],
    };
    expect(() => projectWalk(broken)).toThrow(/names a node the layout does not contain/);
  });

  it('refuses a duplicate node id rather than de-duplicating it', () => {
    const first = FIXTURE_LAYOUT.nodes[0];
    if (first === undefined) throw new Error('fixture is empty');
    const broken: AncestryLayout = {
      ...FIXTURE_LAYOUT,
      nodes: [...FIXTURE_LAYOUT.nodes, { ...first }],
    };
    expect(() => projectWalk(broken)).toThrow(/appears twice/);
  });

  it('refuses an inverted time extent', () => {
    const broken: AncestryLayout = { ...FIXTURE_LAYOUT, timeExtent: [10, 0] };
    expect(() => projectWalk(broken)).toThrow(/inverted/);
  });
});

describe('the time axis is inferred and stated, never assumed', () => {
  it('reads epoch milliseconds', () => {
    expect(interpretTimeAxis(FIXTURE_LAYOUT.timeExtent)).toBe('epoch_ms');
    expect(SCENE.timeUnit).toBe('epoch_ms');
    const fatality = SCENE.nodes.find((node) => node.still);
    expect(yearAt(fatality?.t ?? 0, 'epoch_ms')).toBe(2003);
  });

  it('reads epoch seconds', () => {
    const seconds: [number, number] = [Date.UTC(2003, 4, 17) / 1000, Date.UTC(2024, 2, 28) / 1000];
    expect(interpretTimeAxis(seconds)).toBe('epoch_s');
    expect(yearAt(seconds[0], 'epoch_s')).toBe(2003);
  });

  it('refuses to name a year on an axis that carries no calendar meaning', () => {
    const scene = projectWalk(layoutWithAbstractTime());
    expect(scene.timeUnit).toBe('abstract');
    expect(yearAt(3, 'abstract')).toBeNull();
  });
});

describe('the scene-graph manifest', () => {
  const manifest = sceneGraphOf(SCENE);

  it('declares zero lights — a scene that cannot be lit cannot glow', () => {
    expect(manifest.lightCount).toBe(0);
  });

  it('lists every node and every edge, so the browser spec can compare with the ribbon', () => {
    expect(manifest.nodeIds).toHaveLength(FIXTURE_LAYOUT.nodes.length);
    expect(manifest.edgeKeys).toHaveLength(FIXTURE_LAYOUT.edges.length);
    expect(manifest.stillNodeIds).toEqual(['ev-2003-fatality']);
  });

  it('costs a bounded number of draw calls regardless of node count', () => {
    // one InstancedMesh + one solid LineSegments + one dashed LineSegments + one still mesh
    expect(manifest.bulkDrawCalls).toBe(4);
  });
});

/** The fixture flattened onto a single instant, for the degenerate-extent case. */
function FIXTURE_NODES_AT_ONE_INSTANT(): AncestryLayout {
  const t = FIXTURE_LAYOUT.timeExtent[0];
  return {
    ...FIXTURE_LAYOUT,
    nodes: FIXTURE_LAYOUT.nodes.map((node) => ({ ...node, t })),
    timeExtent: [t, t],
  };
}
