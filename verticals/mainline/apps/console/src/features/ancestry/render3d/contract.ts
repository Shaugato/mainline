// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * `AncestryLayout` — the ONE truth both ancestry renderers consume.
 *
 * ── WHY THIS FILE IS A MIRROR AND NOT AN IMPORT ──────────────────────────────────
 *
 * The layout engine lives in `src/features/ancestry/layout/` and is owned by the
 * ancestry-layout-ribbon worker. This file declares the SAME SHAPE structurally, and
 * `WalkCanvas` accepts anything assignable to it.
 *
 * That is deliberate, and it is the safer of the two available choices:
 *
 *   • A hard `import type { AncestryLayout } from '../layout'` couples the whole
 *     workspace's `tsc --noEmit` to a module this worker does not own and cannot
 *     create. If that module's path or export name differs by one character, the
 *     console does not typecheck — for every worker, not just this one.
 *   • TypeScript is structural. A value produced by the layout engine is assignable to
 *     the interfaces below whenever the two agree, and `tsc` says so at the call site
 *     in `AncestryScreen.tsx` the moment the ribbon worker wires them together. A
 *     disagreement is therefore caught at exactly the place it matters, and nowhere
 *     else is held hostage in the meantime.
 *
 * The shape is copied verbatim from the ancestry-layout-ribbon brief in
 * `docs/leads/workers.json`:
 *
 *     AncestryLayout {
 *       nodes: [{ id, kind:'commit'|'event'|'clause_version',
 *                 x, y, t, severity, virulence, lane, label }],
 *       edges: [{ from, to, basis, inferred:boolean }],
 *       lanes, timeExtent, truncated, closureGen, ancestryComplete
 *     }
 *
 * The two scalar vocabularies (`severity` 0..5, `virulence_class`) come from
 * `contracts/common.schema.json`, which is the wire contract, which is the database's
 * own spelling. This directory does not invent a band, a rank or a synonym.
 *
 * ── WHAT THIS DIRECTORY IS ALLOWED TO DO WITH A LAYOUT ───────────────────────────
 *
 * Add a `z`. That is all. `projection.ts` derives `z` from the `t` that is already in
 * the layout and applies one affine transform to `(x, y)` so the walk fits a frustum.
 * It may not add a node, drop a node, add an edge, drop an edge, re-order, re-rank,
 * re-lane or re-band anything. `projection.test.ts` asserts the identity.
 */

// ── The scalar vocabularies, spelled as the database spells them ─────────────────

/** `mainline.event` severity, 0..5. **5 is a fatality**, and 5 is what stillness means. */
export type Severity = 0 | 1 | 2 | 3 | 4 | 5;

/** `mainline.virulence_class` (`contracts/common.schema.json`), in the enum's own order. */
export type VirulenceClass = 'routine' | 'serious' | 'blood_major' | 'blood_fatal';

/** The three things a node in the walk can be (`ARCHITECTURE.md` §4 — two DAGs, never conflated). */
export type LayoutNodeKind = 'commit' | 'event' | 'clause_version';

/**
 * `mainline.blame_basis`. Carried through the projection untouched so the renderer can
 * mark an inferred link distinctly — an inferred edge shown as though it were asserted
 * is precisely the rubber stamp this product refuses to build.
 */
export type BlameBasis =
  | 'asserted_document'
  | 'asserted_human'
  | 'derived_documentary'
  | 'inferred_semantic';

export const BLAME_BASES: readonly BlameBasis[] = [
  'asserted_document',
  'asserted_human',
  'derived_documentary',
  'inferred_semantic',
];

export function isBlameBasis(value: unknown): value is BlameBasis {
  return (BLAME_BASES as readonly unknown[]).includes(value);
}

// ── The layout, structurally ─────────────────────────────────────────────────────

export interface LayoutNode {
  readonly id: string;
  readonly kind: LayoutNodeKind;
  /** Layout-space horizontal position. Units are the layout engine's; this file assumes none. */
  readonly x: number;
  /** Layout-space vertical position. */
  readonly y: number;
  /** The time coordinate. **This is the third axis.** Monotone: a child never precedes its parent. */
  readonly t: number;
  readonly severity: number;
  readonly virulence: VirulenceClass;
  readonly lane: number;
  readonly label: string;
}

export interface LayoutEdge {
  readonly from: string;
  readonly to: string;
  /**
   * A `mainline.blame_basis` value — but typed `string`, deliberately.
   *
   * The vertical's enum can gain a member without this renderer being rebuilt, and a
   * narrow union here would mean the walk refused to draw an ancestry it understood
   * perfectly well. `isBlameBasis()` is available for a caller that wants the narrow
   * check; this surface does not need one, because it renders `inferred` and never
   * branches on the basis itself.
   */
  readonly basis: string;
  /** `basis === 'inferred_semantic'` as the layout engine decided it. Never re-derived here. */
  readonly inferred: boolean;
}

export interface AncestryLayout {
  readonly nodes: readonly LayoutNode[];
  readonly edges: readonly LayoutEdge[];
  readonly lanes: number;
  /** `[tMin, tMax]`, oldest first. The rail is laid along this interval and nothing else. */
  readonly timeExtent: readonly [number, number];
  readonly truncated: boolean;
  readonly closureGen: number;
  readonly ancestryComplete: boolean;
}

// ── Guards ───────────────────────────────────────────────────────────────────────

/**
 * The severity that confers stillness.
 *
 * Declared here, beside the vocabulary, rather than inside the renderer, because it is a
 * fact about `mainline.event.severity` — "5 is a fatality" — and not a rendering choice.
 * `stillness.ts` re-exports it so a reader of the rule finds it where the rule is.
 */
export const FATALITY_SEVERITY = 5;

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

export function isLayoutNode(value: unknown): value is LayoutNode {
  if (typeof value !== 'object' || value === null) return false;
  const node = value as Partial<LayoutNode>;
  return (
    typeof node.id === 'string' &&
    node.id.length > 0 &&
    (node.kind === 'commit' || node.kind === 'event' || node.kind === 'clause_version') &&
    isFiniteNumber(node.x) &&
    isFiniteNumber(node.y) &&
    isFiniteNumber(node.t) &&
    isFiniteNumber(node.severity) &&
    typeof node.lane === 'number' &&
    typeof node.label === 'string'
  );
}

/**
 * Whether a value can be walked.
 *
 * Deliberately structural and deliberately shallow on the fields this directory does not
 * read: `virulence` is carried but never consulted for geometry, so a payload whose
 * virulence spelling drifts is the EVIDENCE register's problem, not a reason to refuse
 * to draw. What IS checked is every field the geometry depends on, because a NaN in `t`
 * would put a node at an undefined depth and a silently-undefined depth is a lie about
 * when something happened.
 */
export function isAncestryLayout(value: unknown): value is AncestryLayout {
  if (typeof value !== 'object' || value === null) return false;
  const layout = value as Partial<AncestryLayout>;
  if (!Array.isArray(layout.nodes) || !Array.isArray(layout.edges)) return false;
  if (!Array.isArray(layout.timeExtent) || layout.timeExtent.length !== 2) return false;
  const [lo, hi] = layout.timeExtent as readonly unknown[];
  if (!isFiniteNumber(lo) || !isFiniteNumber(hi)) return false;
  if (typeof layout.truncated !== 'boolean') return false;
  if (typeof layout.ancestryComplete !== 'boolean') return false;
  if (!isFiniteNumber(layout.closureGen)) return false;
  if (!isFiniteNumber(layout.lanes)) return false;
  return layout.nodes.every(isLayoutNode);
}
