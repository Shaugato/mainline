// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * NAVIGATION TRUTH — the promise list against the modules that actually ship.
 *
 * `registry.test.ts` proves the machinery: an absent surface produces a card, a lying
 * module is treated as a missing one, an undeclared surface is admitted and sorted last.
 * All of that was true on 2026-08-15 and the served navigation was still wrong, because
 * every one of those assertions is about `buildRegistry`'s BEHAVIOUR and none of them is
 * about the CONTENT of the promise list. Measured against the live URL that morning, the
 * sidebar had nine rows: two dead ends at positions 2 and 3 above every working screen,
 * and two fully-built surfaces at the bottom titled with their bare directory names —
 * `diff` and `evidence` — because neither had ever been added to `DECLARED_SURFACES`.
 *
 * So this file asserts the CONTENT, and it reads the feature modules' own descriptors to
 * do it. The reading is deliberately textual: `import.meta.glob` with `query: '?raw'`
 * gives the bytes of every `surface.tsx` without importing a component, so this gate
 * cannot be satisfied by a module that fails to evaluate and cannot be defeated by one
 * that is too heavy for jsdom to mount.
 *
 * Three properties, and each of them was FALSE at the head this file was written against:
 *
 *   1. Every surface module in the tree is declared. A shipped screen missing from the
 *      promise list is not merely uncatalogued — it is rendered to a judge as a stranger.
 *   2. Where both exist, the promise and the module agree about the screen: same title,
 *      same path, same order, same milestone. Two titles for one screen is a lie the
 *      navigation tells quietly, because only one of them is ever rendered.
 *   3. A promise with no module waits BELOW the screens that carry data, and the entries
 *      waiting there are exactly the ones with no module.
 *
 * What this file does NOT assert, named rather than omitted: `register`.
 * `src/features/propagation/surface.tsx` declares `evidence` while the promise declares
 * `instrument`, which is what `docs/leads/ui.md` §1.1's register table implies for that
 * screen. The navigation and `SurfaceHost` both render the PROMISE's value, so the
 * disagreement is invisible today; resolving it means editing a feature file this worker
 * does not own, and quietly changing the promise to match the module would be the
 * promise list being rewritten to fit the code — the exact move this wave exists to undo.
 * It is reported to the lead instead of being asserted away here.
 */

import { describe, expect, it } from 'vitest';

import {
  DECLARED_SURFACES,
  SURFACE_REGISTRY,
  UNBUILT_ORDER_BASE,
  buildRegistry,
  surfaceIdFromModuleKey,
} from '../../../src/app/surfaces';

/**
 * The bytes of every surface module in the tree, keyed by the glob path.
 *
 * `eager: true` with `query: '?raw'` — text, not modules. A component is never
 * constructed, so a surface whose chunk is heavy, whose imports need WebGL, or whose
 * top level throws is still measured here exactly like every other one.
 */
const MODULE_TEXT: Record<string, unknown> = import.meta.glob('/src/features/*/surface.tsx', {
  query: '?raw',
  import: 'default',
  eager: true,
});

/** The ids that have a module on disk, and the text of each. */
function shippedModules(): Map<string, string> {
  const out = new Map<string, string>();
  for (const [key, value] of Object.entries(MODULE_TEXT)) {
    const id = surfaceIdFromModuleKey(key);
    if (id === null) continue;
    if (typeof value !== 'string') {
      throw new Error(
        `${key} came back as ${typeof value} rather than text. The glob is missing ` +
          "`query: '?raw', import: 'default'`, and every assertion below would be comparing objects.",
      );
    }
    out.set(id, value);
  }
  return out;
}

const SHIPPED = shippedModules();

/** The descriptor literal, from `export const surface` to the brace that closes it. */
function descriptorBody(text: string): string {
  const match = /export const surface: SurfaceDescriptor = \{([\s\S]*?)\n\};/.exec(text);
  if (match?.[1] === undefined) {
    throw new Error(
      'no `export const surface: SurfaceDescriptor = { … };` literal in this module. ' +
        'The descriptor is read as text on purpose (see the header); a module that builds ' +
        'its descriptor some other way must teach this gate how to read it, because a ' +
        'descriptor this gate cannot read is a descriptor nothing compares to the promise.',
    );
  }
  return match[1];
}

function field(body: string, name: string): string {
  const match = new RegExp(`^\\s*${name}:\\s*(.+?),\\s*$`, 'm').exec(body);
  if (match?.[1] === undefined) throw new Error(`the descriptor declares no \`${name}\``);
  const raw = match[1].trim();
  const quoted = /^'(.*)'$/.exec(raw) ?? /^"(.*)"$/.exec(raw);
  return quoted?.[1] ?? raw;
}

describe('every surface that ships is a surface the console promised', () => {
  it('found the surface modules at all', () => {
    // A glob that matches nothing makes every assertion below pass by iterating an empty
    // collection — which is indistinguishable, from the outside, from a navigation that
    // is finally correct.
    expect(SHIPPED.size).toBeGreaterThanOrEqual(7);
  });

  it('declares every one of them, so none is rendered as a self-registered stranger', () => {
    const declared = new Set(DECLARED_SURFACES.map((surface) => surface.id));
    const strangers = [...SHIPPED.keys()].filter((id) => !declared.has(id)).sort();
    expect(
      strangers,
      'these surfaces are built and shipping and are missing from DECLARED_SURFACES. ' +
        'buildRegistry files an undeclared surface at UNDECLARED_ORDER_BASE with its bare ' +
        'directory name as its title, an `unknown` milestone and the promise text "This ' +
        'surface registered itself and is not in the console’s promise list." That rendering ' +
        'is correct and it is what a judge saw for `diff` and `evidence` on 2026-08-15. ' +
        'Add the entry; there is no route table to add it to instead.',
    ).toEqual([]);
  });

  it('agrees with each module about the screen: title, path, order and milestone', () => {
    for (const surface of DECLARED_SURFACES) {
      const text = SHIPPED.get(surface.id);
      if (text === undefined) continue; // A promise with no module. Asserted below instead.
      const body = descriptorBody(text);

      // The navigation renders the PROMISE's value. A module that declares a different
      // title is not overruled — it is unheard, which is worse, because the disagreement
      // never appears on a screen where somebody could notice it.
      expect(field(body, 'id'), `${surface.id}: id`).toBe(surface.id);
      expect(field(body, 'path'), `${surface.id}: path`).toBe(surface.path);
      expect(field(body, 'title'), `${surface.id}: title`).toBe(surface.title);
      expect(Number(field(body, 'order')), `${surface.id}: order`).toBe(surface.order);
      expect(field(body, 'milestone'), `${surface.id}: milestone`).toBe(surface.milestone);
    }
  });
});

describe('the navigation a judge walks, top to bottom', () => {
  it('reads in the order the wave settled on, with the two unbuilt promises last', () => {
    expect(DECLARED_SURFACES.map((surface) => surface.id)).toEqual([
      'overview',
      'gate',
      'diff',
      'custody',
      'evidence',
      'audit',
      'propagation',
      'silence',
      'ancestry',
      'disposition',
    ]);
  });

  it('is what the REAL registry sorts to, not merely what the array happens to hold', () => {
    // `SURFACE_REGISTRY` is built from the live glob against the real filesystem. This is
    // the order the shell iterates; the array literal above is only its input.
    expect(SURFACE_REGISTRY.map((entry) => entry.id)).toEqual(
      DECLARED_SURFACES.map((surface) => surface.id),
    );
  });

  it('opens on the on-ramp and keeps the refusal second', () => {
    expect(DECLARED_SURFACES[0]?.id).toBe('overview');
    expect(DECLARED_SURFACES[1]?.id).toBe('gate');
  });
});

describe('a promise with no module waits below the screens that carry data', () => {
  const banded = DECLARED_SURFACES.filter((surface) => surface.order >= UNBUILT_ORDER_BASE);

  it('holds ancestry and disposition, which is where the wave moved them', () => {
    expect(banded.map((surface) => surface.id)).toEqual(['ancestry', 'disposition']);
  });

  it('holds nothing that has a module — an entry left in the band after its module lands is red', () => {
    const built = banded.filter((surface) => SHIPPED.has(surface.id)).map((surface) => surface.id);
    expect(
      built,
      'these surfaces have shipped and their promise is still parked in the not-built band, ' +
        'so a working screen sorts below every other one for no reason a reader can see. ' +
        'Move the entry back into the running order in the same change that lands the module.',
    ).toEqual([]);
  });

  it('sorts below every screen that has one', () => {
    const highestBuilt = Math.max(
      ...DECLARED_SURFACES.filter((surface) => SHIPPED.has(surface.id)).map(
        (surface) => surface.order,
      ),
    );
    for (const surface of banded) {
      expect(surface.order, `${surface.id} is not below the working screens`).toBeGreaterThan(
        highestBuilt,
      );
    }
  });

  it('still sorts ABOVE an undeclared stranger — waiting is not the same as unpromised', () => {
    const registry = buildRegistry({ '/src/features/fixity/surface.tsx': () => Promise.resolve({}) });
    const stranger = registry.findIndex((entry) => entry.id === 'fixity');
    for (const surface of banded) {
      expect(registry.findIndex((entry) => entry.id === surface.id)).toBeLessThan(stranger);
    }
  });

  it('keeps everything the NOT-BUILT-YET card renders: milestone, owner and promise', () => {
    // The card names who owes the screen and what it owed. Moving an entry down the list
    // must not quietly hollow it out — a promise reduced to a title is a promise withdrawn.
    for (const surface of banded) {
      expect(surface.milestone, `${surface.id}: milestone`).toMatch(/^K[0-9]+$/);
      expect(surface.owner, `${surface.id}: owner`).toMatch(/^ui\/[a-z0-9-]+$/);
      expect(surface.promise.length, `${surface.id}: promise`).toBeGreaterThan(80);
    }

    const ancestry = DECLARED_SURFACES.find((surface) => surface.id === 'ancestry');
    const disposition = DECLARED_SURFACES.find((surface) => surface.id === 'disposition');
    // The two cards, word for word as they were before the reorder. If a future change
    // softens either of these, it is deleting a promise rather than deferring it.
    expect(ancestry?.milestone).toBe('K3');
    expect(ancestry?.owner).toBe('ui/ancestry-layout-ribbon');
    expect(ancestry?.promise).toContain('the printable exhibit form');
    expect(disposition?.milestone).toBe('K5');
    expect(disposition?.owner).toBe('ui/disposition-lattice-modal');
    expect(disposition?.promise).toContain('A person being made to sign');
  });
});

describe('the promise list is still a contract', () => {
  it('is frozen, entry by entry, after everything above', () => {
    expect(Object.isFrozen(DECLARED_SURFACES)).toBe(true);
    for (const surface of DECLARED_SURFACES) expect(Object.isFrozen(surface)).toBe(true);
  });

  it('promises nothing twice — one id, one path, one order each', () => {
    const ids = DECLARED_SURFACES.map((surface) => surface.id);
    const paths = DECLARED_SURFACES.map((surface) => surface.path);
    const orders = DECLARED_SURFACES.map((surface) => surface.order);
    expect(new Set(ids).size).toBe(ids.length);
    expect(new Set(paths).size).toBe(paths.length);
    expect(new Set(orders).size).toBe(orders.length);
  });

  it('says what every surface is FOR, in a sentence, including the ones that opened today', () => {
    for (const surface of DECLARED_SURFACES) {
      expect(surface.promise.length, `${surface.id} promises nothing readable`).toBeGreaterThan(80);
      expect(surface.promise.trim().endsWith('.'), `${surface.id}: promise is not a sentence`).toBe(
        true,
      );
      expect(surface.title.trim(), `${surface.id}: title`).not.toBe(surface.id);
    }
  });
});
