// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * WHAT IS ALLOWED TO BECOME A GLYPH IN THIS REGISTER.
 *
 * Exactly two things (charter §4, A4):
 *
 *   1. a YEAR, derived from a node's `t` against the axis unit the projection inferred;
 *   2. the STILL NODE's own `label` — the one sentence the walk exists to arrive at.
 *
 * Nothing else. Not a commit id, not a severity number, not a virulence band, not an
 * edge basis, and above all not a person: `ARCHITECTURE.md` §11.5's Attribution Rule and
 * I15 say no named human appears, and a screenshot outlives the schema that would have
 * stopped it. `projection.ts` refuses a person-shaped FIELD; this file refuses a
 * person-shaped OPPORTUNITY, by having nowhere for one to go.
 *
 * ── WHY THE LABELS ARE DOM AND NOT SDF ───────────────────────────────────────────
 *
 * Recorded in full in `docs/dimensionality-charter.md` §3.1. In one line:
 * `troika-three-text` with no `font` prop fetches a webfont from `fonts.gstatic.com`,
 * which is a network dependency inside the one surface whose value is that it captures
 * deterministically and serves from a static directory with no credentials. DOM text is
 * selectable, screen-reader-legible, free in the bundle, and rasterises identically
 * under `--disable-lcd-text`.
 */

import { yearAt, type WalkScene } from './projection';

/** Hard ceiling on labels, at any tier. Beyond this the rail reads as a ruler, not a walk. */
export const MAX_LABELS = 24;

export type WalkLabelKind = 'year' | 'still';

export interface WalkLabel {
  /** Stable across renders and across tiers; used as the React key and the DOM id suffix. */
  readonly id: string;
  readonly kind: WalkLabelKind;
  readonly text: string;
  readonly position: readonly [number, number, number];
}

/**
 * The label set for a scene, as a pure function of the scene and the detail stride.
 *
 * Deterministic and order-stable: years ascend, and the still label is last, so the DOM
 * order is the reading order and a screen reader walks the corpus oldest-first.
 */
export function buildLabels(scene: WalkScene, stride = 1): readonly WalkLabel[] {
  const labels: WalkLabel[] = [];

  if (scene.timeUnit !== 'abstract') {
    // One marker per year, anchored to the OLDEST node in that year, so the marker sits
    // where the year begins rather than at an arithmetic mean nothing happened at.
    const earliestByYear = new Map<number, { t: number; x: number; y: number; z: number }>();
    for (const node of scene.nodes) {
      const year = yearAt(node.t, scene.timeUnit);
      if (year === null) continue;
      const existing = earliestByYear.get(year);
      if (existing === undefined || node.t < existing.t) {
        earliestByYear.set(year, { t: node.t, x: node.x, y: node.y, z: node.z });
      }
    }

    const years = [...earliestByYear.keys()].sort((a, b) => a - b);
    const step = Math.max(1, Math.trunc(stride));
    for (let index = 0; index < years.length; index += step) {
      const year = years[index];
      if (year === undefined) continue;
      const anchor = earliestByYear.get(year);
      if (anchor === undefined) continue;
      labels.push({
        id: `year:${year}`,
        kind: 'year',
        text: String(year),
        // Raised clear of the nodes so a year never sits on top of a fact.
        position: [anchor.x, anchor.y + 2.4, anchor.z],
      });
    }
  }

  // Thin from the PRESENT backwards if the cap is hit, so the deep past — the part of
  // the corpus a reader cannot date from memory — keeps its markers.
  while (labels.length > MAX_LABELS - scene.stillNodes.length) {
    labels.pop();
  }

  for (const node of scene.stillNodes) {
    labels.push({
      id: `still:${node.id}`,
      kind: 'still',
      text: node.label,
      position: [node.x, node.y + 3.2, node.z],
    });
  }

  return Object.freeze(labels);
}
