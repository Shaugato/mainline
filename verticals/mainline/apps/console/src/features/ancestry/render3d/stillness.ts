// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE STILLNESS RULE.
 *
 *   > In the MEMORY register the severity-5 node is the only object in the scene that
 *   > never moves, never scales, never emits and never responds to hover. Everything
 *   > else moves past it.
 *
 * `docs/leads/ui.md` §1.2.1 · D10 · `docs/dimensionality-charter.md` §1.
 *
 * Stillness marks the dead. Motion is for the living record. That is the design idea,
 * and this file is the reason it is a property of the build rather than a property of
 * whoever last edited the scene.
 *
 * ── WHY THE RULE NEEDS A FILE AT ALL ─────────────────────────────────────────────
 *
 * A comment saying "do not animate the fatality" survives exactly one refactor. What
 * survives is a mechanism with two independent halves, which is the same shape the
 * kernel uses for everything else in this product:
 *
 *   PROJECT — `still` is DERIVED from the layout's `severity` by `projection.ts`. No
 *             renderer can supply it, because `WalkNode` is only ever constructed by
 *             the projection. (P2: a gate reads a column a trigger wrote.)
 *   REFUSE  — `assertAnimatable()` throws when a per-frame mutation names a still node,
 *             and `stillnessViolations()` audits a registry that was built without
 *             going through the door.
 *
 * The audit exists because the door can be walked around: somebody can push an entry
 * onto the registry's array by hand, or build the array literal directly. One is a
 * door and one is a search, and this surface has both.
 */

import { FATALITY_SEVERITY } from './contract';

export { FATALITY_SEVERITY };

/**
 * The one predicate.
 *
 * `severity === 5` and nothing else. Not `>= 5` — the wire contract caps severity at 5
 * (`contracts/common.schema.json`), so `>= 5` would silently accept an out-of-contract
 * 6 and give it the same treatment as a fatality without anyone deciding that. Not
 * `virulence === 'blood_fatal'` either: virulence is a BAND over a closure's maximum,
 * so a routine commit inside a fatal closure carries `blood_fatal` and is emphatically
 * not the dead node.
 */
export function isStillSeverity(severity: number): boolean {
  return severity === FATALITY_SEVERITY;
}

/** The minimum a thing must expose to be judged by this rule. */
export interface StillnessSubject {
  readonly id: string;
  readonly severity: number;
}

export function isStillNode(node: StillnessSubject): boolean {
  return isStillSeverity(node.severity);
}

/**
 * Every kind of per-frame mutation this scene is capable of performing.
 *
 * The list is CLOSED, and that is the load-bearing part. A registry keyed on a free
 * string would let a new animation be added without the rule noticing; a registry keyed
 * on this union makes adding a kind a deliberate edit to the file that also holds the
 * refusal, right under the sentence explaining why the refusal is there.
 */
export type MutationKind =
  | 'hover-scale'
  | 'pointer-proximity'
  | 'rail-travel'
  | 'label-fade'
  | 'edge-dash-offset'
  | 'instance-matrix';

/** One registered per-frame mutation. */
export interface MutationEntry {
  readonly kind: MutationKind;
  /**
   * The node this mutation writes to, or `null` for a mutation that targets no node at
   * all — the camera's own travel along the rail is the only such case, and it is the
   * reason `null` exists rather than a sentinel id that could collide with a real one.
   */
  readonly targetNodeId: string | null;
  /** Free text, rendered in the violation message. A violation must say what tried it. */
  readonly source: string;
}

export class StillnessViolationError extends Error {
  readonly nodeId: string;
  readonly mutationKind: MutationKind;

  constructor(nodeId: string, mutationKind: MutationKind, source: string) {
    super(
      `THE STILLNESS RULE (docs/dimensionality-charter.md §1): "${source}" tried to register a ` +
        `'${mutationKind}' mutation against node ${nodeId}, whose severity is ${FATALITY_SEVERITY}. ` +
        `The severity-5 node never moves, never scales, never emits and never responds to hover. ` +
        `Everything else moves past it. If this node should be animated, the fix is not here — the ` +
        `layout has mis-stated a severity.`,
    );
    this.name = 'StillnessViolationError';
    this.nodeId = nodeId;
    this.mutationKind = mutationKind;
  }
}

/** A violation found by the audit rather than refused at the door. */
export interface StillnessViolation {
  readonly nodeId: string;
  readonly mutationKind: MutationKind;
  readonly source: string;
}

/**
 * THE DOOR. Throws when `entry` names a still node.
 *
 * `severityOf` is passed in rather than read from a module-level scene, so the rule is a
 * pure function and the test that proves it can construct the violating case in three
 * lines with no renderer, no canvas and no GPU.
 *
 * An entry naming a node the scene does not contain is ALSO refused. A mutation pointed
 * at an unknown id cannot be shown to be safe, and "cannot be shown to be safe" resolves
 * toward the refusal everywhere else in this system (P3).
 */
export function assertAnimatable(
  entry: MutationEntry,
  severityOf: (nodeId: string) => number | undefined,
): void {
  if (entry.targetNodeId === null) return;
  const severity = severityOf(entry.targetNodeId);
  if (severity === undefined) {
    throw new Error(
      `THE STILLNESS RULE: "${entry.source}" registered a '${entry.kind}' mutation against node ` +
        `${entry.targetNodeId}, which is not in the scene. A mutation whose target cannot be ` +
        `resolved cannot be shown to obey the rule, so it is refused.`,
    );
  }
  if (isStillSeverity(severity)) {
    throw new StillnessViolationError(entry.targetNodeId, entry.kind, entry.source);
  }
}

/**
 * THE SEARCH. Audits a whole registry against a scene and returns every violation.
 *
 * This is what `stillness.test.ts` runs over the registry the shipped scene actually
 * builds, and it is what catches an entry that never passed through `assertAnimatable`.
 * It returns rather than throws: an audit that stops at the first finding reports one
 * violation when there are four.
 */
export function stillnessViolations(
  entries: readonly MutationEntry[],
  severityOf: (nodeId: string) => number | undefined,
): readonly StillnessViolation[] {
  const found: StillnessViolation[] = [];
  for (const entry of entries) {
    if (entry.targetNodeId === null) continue;
    const severity = severityOf(entry.targetNodeId);
    if (severity !== undefined && isStillSeverity(severity)) {
      found.push({
        nodeId: entry.targetNodeId,
        mutationKind: entry.kind,
        source: entry.source,
      });
    }
  }
  return found;
}
