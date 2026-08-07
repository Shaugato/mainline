// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The surface registry (D8).
 *
 * There is no central route table. Every feature worker adds exactly one file —
 * `src/features/<id>/surface.tsx` exporting a `SurfaceDescriptor` named `surface` —
 * and it appears. Two consequences, both deliberate:
 *
 *   • Zero cross-worker file collisions. Eighty workers, no shared route file.
 *   • The cut ladder (BUILD_PLAN §10.2) becomes `rm -r src/features/<id>` with a
 *     TRUTHFUL UI consequence: the surface renders a NOT-BUILT-YET card naming the
 *     milestone that owes it, rather than vanishing from the navigation as though it
 *     had never been promised.
 *
 * `DECLARED_SURFACES` below is not a route table — it is the console's list of
 * PROMISES. Nothing here can make a surface exist; it only makes an absence nameable.
 */

import type { ComponentType } from 'react';

/** The three registers (ui.md §1.1). Enforced as an import boundary in eslint.config.js. */
export const REGISTERS = ['evidence', 'instrument', 'memory'] as const;
export type Register = (typeof REGISTERS)[number];

/** What a feature module must export as `surface`. */
export interface SurfaceDescriptor {
  readonly id: string;
  readonly path: string;
  readonly title: string;
  readonly register: Register;
  readonly order: number;
  readonly milestone: string;
  readonly Component: ComponentType;
}

/** What the console promised, before anybody built it. */
export interface DeclaredSurface {
  readonly id: string;
  readonly path: string;
  readonly title: string;
  readonly register: Register;
  readonly order: number;
  readonly milestone: string;
  /** The worker in docs/leads/workers.json that owes this surface. */
  readonly owner: string;
  /** One line, rendered on the NOT-BUILT-YET card. Says what the screen is FOR. */
  readonly promise: string;
}

const DECLARED = [
  {
    id: 'gate',
    path: '/gate',
    title: 'Gate — the refusal',
    register: 'evidence',
    order: 10,
    milestone: 'K5',
    owner: 'ui/gate-refusal-screen',
    promise:
      'The permit branch with the refusal bar: the constraint name and the SQLSTATE the database reported, the minimal unsatisfiable subset, the nearest admissible alternative, and the six projected counters that welded the gate shut.',
  },
  {
    id: 'ancestry',
    path: '/ancestry',
    title: 'Ancestry — the blame walk',
    register: 'evidence',
    order: 20,
    milestone: 'K3',
    owner: 'ui/ancestry-layout-ribbon',
    promise:
      'One deterministic layout, two renderers. The ribbon is the printable exhibit form and the default; the dimensional walk is a lazy chunk in the MEMORY register that carries no fact the ribbon lacks.',
  },
  {
    id: 'disposition',
    path: '/disposition',
    title: 'Disposition — the signature',
    register: 'evidence',
    order: 30,
    milestone: 'K5',
    owner: 'ui/disposition-lattice-modal',
    promise:
      'A person being made to sign. Lattice-driven fields, a per-check defeater vocabulary with no global "not applicable", the reading-floor meter, and a countersigner field that appears because the clearance lattice requires it — not because a flag turned it on.',
  },
  {
    id: 'custody',
    path: '/custody',
    title: 'Custody — the chain',
    register: 'evidence',
    order: 40,
    milestone: 'K2',
    owner: 'ui/verifier-custody-room',
    promise:
      'The gap-free ledger, its checkpoint signature and its inclusion and consistency proofs — all recomputed in this browser from the same bytes the offline verifier consumes.',
  },
  {
    id: 'audit',
    path: '/audit',
    title: 'Audit — the MCP surface',
    register: 'evidence',
    order: 50,
    milestone: 'K6',
    owner: 'ui/verifier-custody-room',
    promise:
      'Every question the read-only auditor account asked, the statement it sent, the plan fragment it got back, and the row and byte caps it ran under.',
  },
  {
    id: 'propagation',
    path: '/propagation',
    title: 'Propagation — where the lesson travelled',
    register: 'instrument',
    order: 60,
    milestone: 'K4',
    owner: 'ui/propagation-silence-ledger',
    promise:
      'Which sibling sites took the control change, which did not, and what the system knows about the difference.',
  },
  {
    id: 'silence',
    path: '/silence',
    title: 'Silence — what was not surfaced',
    register: 'evidence',
    order: 70,
    milestone: 'K4',
    owner: 'ui/propagation-silence-ledger',
    promise:
      'Every precursor the recall declined to surface, with its arithmetic: the score, the threshold, the universe it was drawn from, and whether exhaustion could be certified at all.',
  },
] as const satisfies readonly DeclaredSurface[];

for (const surface of DECLARED) {
  Object.freeze(surface);
}
Object.freeze(DECLARED);

/** The promises. Frozen — a surface list a feature worker can mutate is not a contract. */
export const DECLARED_SURFACES: readonly DeclaredSurface[] = DECLARED;

/** The ids the console is prepared to address by name. */
export type DeclaredSurfaceId = (typeof DECLARED)[number]['id'];

export type SurfaceStatus = 'loadable' | 'declared-missing' | 'undeclared';

export type SurfaceLoader = () => Promise<unknown>;
export type SurfaceModules = Record<string, SurfaceLoader>;

export interface SurfaceEntry {
  readonly id: string;
  readonly path: string;
  readonly title: string;
  readonly register: Register;
  readonly order: number;
  readonly milestone: string;
  readonly owner: string;
  readonly promise: string;
  readonly status: SurfaceStatus;
  /** `null` exactly when `status === 'declared-missing'`. */
  readonly load: SurfaceLoader | null;
}

/**
 * Undeclared surfaces sort after every promise. A surface that self-registered without
 * appearing in `DECLARED_SURFACES` is legal — that is what self-registration means —
 * but it does not get to jump the queue in front of a screen the console promised.
 */
const UNDECLARED_ORDER_BASE = 1000;

/**
 * The glob key shape, and the only one. Exactly one directory deep, lowercase, and
 * named `surface.tsx`. A nested `surface.tsx` (a panel, a sub-view) is NOT a surface;
 * admitting one would let a feature worker mount a second screen the promise list has
 * never heard of.
 */
const MODULE_KEY = /^\/src\/features\/([a-z][a-z0-9-]*)\/surface\.tsx$/;

export function surfaceIdFromModuleKey(key: string): string | null {
  const match = MODULE_KEY.exec(key);
  return match?.[1] ?? null;
}

export function buildRegistry(
  modules: SurfaceModules,
  declared: readonly DeclaredSurface[] = DECLARED_SURFACES,
): readonly SurfaceEntry[] {
  const loaders = new Map<string, SurfaceLoader>();
  for (const [key, loader] of Object.entries(modules)) {
    const id = surfaceIdFromModuleKey(key);
    if (id !== null) loaders.set(id, loader);
  }

  const entries: SurfaceEntry[] = declared.map((surface) => {
    const load = loaders.get(surface.id) ?? null;
    return {
      id: surface.id,
      path: surface.path,
      title: surface.title,
      register: surface.register,
      order: surface.order,
      milestone: surface.milestone,
      owner: surface.owner,
      promise: surface.promise,
      status: load === null ? 'declared-missing' : 'loadable',
      load,
    };
  });

  const declaredIds = new Set(declared.map((surface) => surface.id));
  const extras = [...loaders.keys()].filter((id) => !declaredIds.has(id)).sort();
  extras.forEach((id, index) => {
    entries.push({
      id,
      path: `/${id}`,
      title: id,
      // The most restrictive register is the honest default: a surface nobody declared
      // has not had its register reviewed, and EVIDENCE forbids the most.
      register: 'evidence',
      order: UNDECLARED_ORDER_BASE + index,
      milestone: 'unknown',
      owner: 'unknown',
      promise: 'This surface registered itself and is not in the console’s promise list.',
      status: 'undeclared',
      load: loaders.get(id) ?? null,
    });
  });

  entries.sort((a, b) => a.order - b.order || a.id.localeCompare(b.id));
  return entries;
}

export type SurfaceValidation =
  | { readonly ok: true; readonly descriptor: SurfaceDescriptor }
  | { readonly ok: false; readonly reason: string };

function isRegister(value: unknown): value is Register {
  return (REGISTERS as readonly string[]).includes(value as string);
}

/**
 * A module that lies about itself is treated exactly like a module that is not there.
 *
 * The reason string is rendered verbatim on the NOT-BUILT-YET card. It is written for
 * the worker who has to fix it, because that is who will read it.
 */
export function validateSurfaceModule(id: string, mod: unknown): SurfaceValidation {
  const where = `/src/features/${id}/surface.tsx`;

  if (typeof mod !== 'object' || mod === null) {
    return { ok: false, reason: `${where} did not evaluate to a module object (got ${typeof mod}).` };
  }

  const surface = (mod as { surface?: unknown }).surface;
  if (typeof surface !== 'object' || surface === null) {
    return {
      ok: false,
      reason: `${where} has no \`surface\` export. A feature module must export \`export const surface: SurfaceDescriptor\`.`,
    };
  }

  const d = surface as Record<string, unknown>;

  if (typeof d.id !== 'string' || d.id !== id) {
    return {
      ok: false,
      reason: `${where} declares id ${JSON.stringify(d.id)}; the directory name requires "${id}". The directory is the identity — rename one of them.`,
    };
  }
  if (typeof d.path !== 'string' || !d.path.startsWith('/')) {
    return { ok: false, reason: `${where} declares a path that is not rooted: ${JSON.stringify(d.path)}.` };
  }
  if (typeof d.title !== 'string' || d.title.trim() === '') {
    return { ok: false, reason: `${where} declares no title. A surface with no title cannot appear in navigation.` };
  }
  if (!isRegister(d.register)) {
    return {
      ok: false,
      reason: `${where} declares register ${JSON.stringify(d.register)}, which is not one of ${REGISTERS.join(', ')} (ui.md §1.1).`,
    };
  }
  if (typeof d.order !== 'number' || !Number.isFinite(d.order)) {
    return { ok: false, reason: `${where} declares a non-numeric order: ${JSON.stringify(d.order)}.` };
  }
  if (typeof d.milestone !== 'string' || d.milestone.trim() === '') {
    return {
      ok: false,
      reason: `${where} names no milestone. Every surface must say which milestone owns it, so that an absence can be attributed.`,
    };
  }
  if (typeof d.Component !== 'function') {
    return {
      ok: false,
      reason: `${where} exports a surface whose Component is ${typeof d.Component}, not a React component function.`,
    };
  }

  return { ok: true, descriptor: surface as unknown as SurfaceDescriptor };
}

/**
 * The live glob. Vite resolves this at build time against the real filesystem, so a
 * surface that has not been written produces no key — which is exactly the signal
 * `buildRegistry` turns into a NOT-BUILT-YET card.
 *
 * `eager: false` keeps every feature surface off the critical path (D13): the
 * evidentiary shell must paint a refusal without loading a single feature chunk.
 */
const MODULES = import.meta.glob('/src/features/*/surface.tsx', { eager: false }) as SurfaceModules;

export const SURFACE_REGISTRY: readonly SurfaceEntry[] = buildRegistry(MODULES);

export function findSurfaceByPath(
  path: string,
  entries: readonly SurfaceEntry[] = SURFACE_REGISTRY,
): SurfaceEntry | null {
  return entries.find((entry) => entry.path === path) ?? null;
}
