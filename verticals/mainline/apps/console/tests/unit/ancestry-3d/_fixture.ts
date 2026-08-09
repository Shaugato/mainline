// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The fixture every MEMORY-register test walks.
 *
 * It is the shape `docs/leads/ui.md` §1.2 describes in prose: a commit DAG walked
 * backwards through twenty-one years and three identity-preserving reflows to a 2003
 * fatality. Small enough to reason about by hand, and structurally complete — it has
 * both DAGs (`ARCHITECTURE.md` §4: history and blame, never conflated), an
 * `inferred_semantic` edge that must be marked distinctly, more than one lane, and
 * exactly one severity-5 node.
 *
 * NO PERSON APPEARS IN IT, and that is not incidental: `attribution.test.ts` adds one
 * on purpose and asserts the renderer refuses it.
 *
 * Not a `.test.ts`, so Vitest does not collect it.
 */

import type {
  AncestryLayout,
  LayoutEdge,
  LayoutNode,
} from '../../../src/features/ancestry/render3d/contract';

const YEAR = (year: number, month = 0, day = 1): number => Date.UTC(year, month, day);

/**
 * Nine nodes. The blame DAG's terminal event is `ev-2003-fatality`; everything else is
 * the history DAG walking forward to the clause version a permit would cite today.
 *
 * SEVERITY AND VIRULENCE ARE DIFFERENT FACTS, and the fixture is built to keep them
 * apart. `severity` is `mainline.event.severity` — a property of an EVENT, so a commit
 * carries 0. `virulence` is `clause_blame_closure`'s BAND over the closure's maximum, so
 * every commit downstream of the 2003 fatality carries `blood_fatal` while being
 * emphatically not the dead node. A stillness rule that read virulence would freeze the
 * whole right-hand lane.
 */
export const FIXTURE_NODES: readonly LayoutNode[] = [
  {
    id: 'ev-2003-fatality',
    kind: 'event',
    x: 0,
    y: 0,
    t: YEAR(2003, 4, 17),
    severity: 5,
    virulence: 'blood_fatal',
    lane: 0,
    label: 'Fall from height — mobile plant access platform, no secondary restraint',
  },
  {
    id: 'cm-2003-origin',
    kind: 'commit',
    x: 60,
    y: 40,
    t: YEAR(2003, 8, 2),
    severity: 0,
    virulence: 'blood_fatal',
    lane: 1,
    label: 'Introduce secondary-restraint clause',
  },
  {
    id: 'ev-2009-nearmiss',
    kind: 'event',
    x: 0,
    y: 90,
    t: YEAR(2009, 1, 11),
    severity: 3,
    virulence: 'blood_major',
    lane: 0,
    label: 'Near miss — restraint anchor not verified before elevation',
  },
  {
    id: 'cm-2009-strengthen',
    kind: 'commit',
    x: 60,
    y: 130,
    t: YEAR(2009, 2, 20),
    severity: 0,
    virulence: 'blood_major',
    lane: 1,
    label: 'Strengthen: anchor verification becomes a hold point',
  },
  {
    id: 'ev-2014-audit',
    kind: 'event',
    x: 0,
    y: 180,
    t: YEAR(2014, 6, 4),
    severity: 2,
    virulence: 'serious',
    lane: 0,
    label: 'Audit finding — hold point recorded after the fact on three shifts',
  },
  {
    id: 'cm-2014-restate',
    kind: 'commit',
    x: 60,
    y: 220,
    t: YEAR(2014, 7, 15),
    severity: 0,
    virulence: 'serious',
    lane: 1,
    label: 'Restate: hold point wording, no control change',
  },
  {
    id: 'cm-2019-reflow',
    kind: 'commit',
    x: 60,
    y: 300,
    t: YEAR(2019, 10, 6),
    severity: 0,
    virulence: 'serious',
    lane: 1,
    label: 'Identity-preserving reflow — clause renumbered 4.2.1 → 6.1.3',
  },
  {
    id: 'cm-2024-weaken',
    kind: 'commit',
    x: 60,
    y: 380,
    t: YEAR(2024, 2, 28),
    severity: 0,
    virulence: 'serious',
    lane: 1,
    label: 'Weaken: hold point becomes advisory below 2 m',
  },
  {
    id: 'cv-2024-current',
    kind: 'clause_version',
    x: 130,
    y: 420,
    t: YEAR(2024, 2, 28),
    severity: 0,
    virulence: 'serious',
    lane: 2,
    label: 'Clause 6.1.3 — current',
  },
];

/**
 * Eleven edges. One is `inferred_semantic`, which the schema forbids from ever reaching
 * state `active` and which the renderer must mark distinctly at display.
 */
export const FIXTURE_EDGES: readonly LayoutEdge[] = [
  { from: 'ev-2003-fatality', to: 'cm-2003-origin', basis: 'asserted_document', inferred: false },
  { from: 'ev-2009-nearmiss', to: 'ev-2003-fatality', basis: 'asserted_human', inferred: false },
  { from: 'ev-2009-nearmiss', to: 'cm-2009-strengthen', basis: 'asserted_document', inferred: false },
  { from: 'cm-2003-origin', to: 'cm-2009-strengthen', basis: 'derived_documentary', inferred: false },
  { from: 'ev-2014-audit', to: 'cm-2014-restate', basis: 'asserted_document', inferred: false },
  { from: 'ev-2014-audit', to: 'ev-2009-nearmiss', basis: 'inferred_semantic', inferred: true },
  { from: 'cm-2009-strengthen', to: 'cm-2014-restate', basis: 'derived_documentary', inferred: false },
  { from: 'cm-2014-restate', to: 'cm-2019-reflow', basis: 'derived_documentary', inferred: false },
  { from: 'cm-2019-reflow', to: 'cm-2024-weaken', basis: 'derived_documentary', inferred: false },
  { from: 'cm-2024-weaken', to: 'cv-2024-current', basis: 'derived_documentary', inferred: false },
  { from: 'cm-2003-origin', to: 'cv-2024-current', basis: 'inferred_semantic', inferred: true },
];

export const FIXTURE_LAYOUT: AncestryLayout = Object.freeze({
  nodes: FIXTURE_NODES,
  edges: FIXTURE_EDGES,
  lanes: 3,
  timeExtent: [YEAR(2003, 4, 17), YEAR(2024, 2, 28)] as const,
  truncated: false,
  closureGen: 7,
  ancestryComplete: true,
});

/** The id every stillness assertion is about. Named once so no test re-derives it. */
export const STILL_NODE_ID = 'ev-2003-fatality';

/** A layout with the same shape but no fatality — nothing in it is still. */
export function layoutWithoutFatality(): AncestryLayout {
  return {
    ...FIXTURE_LAYOUT,
    nodes: FIXTURE_NODES.map((node) =>
      node.severity === 5 ? { ...node, severity: 4, virulence: 'blood_major' as const } : node,
    ),
  };
}

/** A layout whose `t` axis carries no calendar meaning — the `abstract` unit. */
export function layoutWithAbstractTime(): AncestryLayout {
  const nodes = FIXTURE_NODES.map((node, index) => ({ ...node, t: index }));
  return {
    ...FIXTURE_LAYOUT,
    nodes,
    timeExtent: [0, FIXTURE_NODES.length - 1] as const,
  };
}
