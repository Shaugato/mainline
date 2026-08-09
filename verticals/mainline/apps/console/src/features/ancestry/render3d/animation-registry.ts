// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE ANIMATION REGISTRY.
 *
 * Every per-frame mutation in the MEMORY register passes through this object, and the
 * object knows the stillness rule. Nothing in this directory is allowed to move a thing
 * without saying, in a data structure, which thing it is moving and why.
 *
 * That is a strange amount of ceremony for a scene with six moving parts, and it is the
 * point. `docs/leads/ui.md` D10 requires the stillness rule to be "asserted by a unit
 * test over the animation graph, not by taste". A unit test can only be written over an
 * animation graph that EXISTS. So the graph exists, it is small, it is the real one the
 * renderer consults, and it is the thing the test reads.
 *
 * ── HOW THE RENDERER USES IT ─────────────────────────────────────────────────────
 *
 *   1. `WalkScene` builds one registry per scene, from the projected `WalkScene`.
 *   2. Every component that mutates something per frame declares its mutation once,
 *      at build time, via `register()`. `register()` throws on a still node.
 *   3. The hover system calls `mayAnimate(nodeId)` before it touches an instance
 *      matrix. That is the runtime half: even if a future edit forgot to register, the
 *      still node cannot be scaled, because the question is asked at the moment of the
 *      write and the answer is derived from the projected `still` flag.
 *
 * (2) is the door and (3) is the lock. `stillnessViolations()` in `stillness.ts` is the
 * search, and `stillness.test.ts` runs all three against the shipped scene.
 */

import {
  assertAnimatable,
  isStillSeverity,
  stillnessViolations,
  type MutationEntry,
  type MutationKind,
  type StillnessViolation,
} from './stillness';

/** The minimum a scene must expose for the registry to police it. */
export interface RegistrySubject {
  readonly id: string;
  readonly severity: number;
}

export interface AnimationRegistry {
  /**
   * Declare a per-frame mutation. THROWS if it targets a still node, or a node that is
   * not in the scene.
   */
  register: (kind: MutationKind, targetNodeId: string | null, source: string) => void;
  /** Everything registered, in registration order. Frozen copy; the caller cannot mutate it. */
  entries: () => readonly MutationEntry[];
  /**
   * The runtime lock. `false` for a still node and for an unknown node.
   *
   * Deliberately total and deliberately quiet: it is called inside a pointer handler at
   * up to one call per frame, and a throw there would take down the canvas over a mouse
   * position. The throw belongs at `register()`, which runs once.
   */
  mayAnimate: (nodeId: string) => boolean;
  /** The audit. Empty for a well-formed scene. */
  violations: () => readonly StillnessViolation[];
  /** Ids the registry considers still. Exposed so tests do not re-derive the rule. */
  stillNodeIds: () => readonly string[];
}

/**
 * Builds a registry over a fixed set of nodes.
 *
 * The severity map is captured ONCE, from the projected scene. It is not re-read from
 * the layout, because the projected `still` flag and the severity that produced it must
 * not be able to disagree — P2, one hop downstream: the thing the gate reads is the
 * thing the projection wrote.
 */
export function createAnimationRegistry(nodes: readonly RegistrySubject[]): AnimationRegistry {
  const severityById = new Map<string, number>();
  for (const node of nodes) {
    severityById.set(node.id, node.severity);
  }
  const severityOf = (nodeId: string): number | undefined => severityById.get(nodeId);

  const entries: MutationEntry[] = [];

  return {
    register(kind, targetNodeId, source) {
      const entry: MutationEntry = { kind, targetNodeId, source };
      assertAnimatable(entry, severityOf);
      entries.push(entry);
    },
    entries() {
      return Object.freeze(entries.slice());
    },
    mayAnimate(nodeId) {
      const severity = severityOf(nodeId);
      if (severity === undefined) return false;
      return !isStillSeverity(severity);
    },
    violations() {
      return stillnessViolations(entries, severityOf);
    },
    stillNodeIds() {
      const still: string[] = [];
      for (const [id, severity] of severityById) {
        if (isStillSeverity(severity)) still.push(id);
      }
      return Object.freeze(still);
    },
  };
}

/**
 * The registry the shipped scene builds, as a pure function of the scene's nodes.
 *
 * Extracted from the React tree on purpose: `stillness.test.ts` calls THIS, not a
 * rendered canvas, so the test asserts the real registration list rather than a
 * hand-written copy of it that could drift. If a component starts mutating something
 * new, it registers here, and the test reads it here.
 *
 * The list is exhaustive for the current scene:
 *
 *   rail-travel        the camera. Targets no node — the camera is not a node, and the
 *                      scene stands still while the observer moves. That asymmetry IS
 *                      the surface.
 *   hover-scale        one living node under the pointer.
 *   pointer-proximity  the living nodes near the pointer.
 *   edge-dash-offset   the inferred-edge material's dash phase.
 *   label-fade         the DOM label layer's opacity as a label crosses the frustum.
 *
 * `instance-matrix` is declared in `MutationKind` and is NOT registered here: the living
 * nodes' instance matrices are written once at build time and never per frame. It exists
 * in the union so that a future edit which starts writing them per frame has a name to
 * register under, rather than a reason to widen the type.
 */
export function buildSceneRegistry(nodes: readonly RegistrySubject[]): AnimationRegistry {
  const registry = createAnimationRegistry(nodes);
  registry.register('rail-travel', null, 'RailsRig: the camera walks the time axis');
  registry.register('edge-dash-offset', null, 'Edges: the inferred-edge dash phase');
  registry.register('label-fade', null, 'Labels: DOM label opacity across the frustum');
  for (const node of nodes) {
    if (registry.mayAnimate(node.id)) {
      registry.register('hover-scale', node.id, 'Nodes: pointer hover on a living node');
    }
  }
  return registry;
}
