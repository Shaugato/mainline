// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE MEMORY PALETTE — four colours, and no fifth exists.
 *
 * `docs/leads/ui.md` §1.2.3:
 *
 *   > No emissive vocabulary. No bloom, no lens flare, no god rays, no particles, no
 *   > depth of field. Monochrome plus the single severity accent, the same token set as
 *   > EVIDENCE. **The 3D surface uses FEWER colours than the tables, not more.**
 *
 * That last sentence is the whole thesis of this file, and `palette.test.ts` turns it
 * into arithmetic: it counts the colour tokens `TOKEN_LAW` permits the EVIDENCE tables
 * and asserts this list is strictly shorter. It is not a claim in a comment.
 *
 * ── WHY THE VALUES ARE MIRRORED HERE AT ALL ──────────────────────────────────────
 *
 * three.js cannot parse `oklch()`. `THREE.Color.setStyle` handles hex, `rgb()`, `hsl()`
 * and the named colours, and nothing else — so a token read straight out of
 * `getComputedStyle` would silently become black, and a scene whose severity accent had
 * silently become black is a scene that has stopped saying anything.
 *
 * So the pipeline is: read the custom property from the live document if there is one →
 * parse the OKLCH → convert to sRGB with the SAME code the contrast gate uses
 * (`src/design/color.ts`) → hand three.js a hex string. When there is no document (a
 * unit test, a Node import), fall back to the authored literal below.
 *
 * The fallback is a mirror, and a mirror is a lie waiting to happen — so `palette.test.ts`
 * parses `src/design/tokens.css` and asserts every literal here is byte-identical to the
 * declaration there. Same discipline as `motion.test.ts` and the duration tokens.
 */

import { oklchToSrgb, parseOklch, toHex, type Srgb } from '../../../design/color';

/** The four roles the scene has. There is no fifth role, so there is no fifth colour. */
export type PaletteRole = 'void' | 'edge' | 'living' | 'still';

export interface PaletteEntry {
  readonly role: PaletteRole;
  /** The custom property. Must be one the MEMORY register is permitted (`tokenAllowedIn`). */
  readonly token: string;
  /** The authored value in `src/design/tokens.css`'s dark register, verbatim. */
  readonly authored: string;
  /** What it is for, in one clause. */
  readonly purpose: string;
}

/**
 * THE ENTIRE PALETTE.
 *
 * `--tp-ok` — the console's only green — is deliberately absent and could not be added:
 * `TOKEN_LAW` marks it EVIDENCE-only, and `palette.test.ts` asserts every entry here is
 * permitted in the MEMORY register. There is no green tick without a recomputation
 * behind it, and there is no recomputation in a scene.
 *
 * `--tp-refuse` is absent too, and for a sharper reason: a refusal is a thing the
 * database said, and the MEMORY register renders no verbatim claim. The accent in this
 * scene is a severity band, not a state.
 */
export const MEMORY_PALETTE: readonly PaletteEntry[] = [
  {
    role: 'void',
    token: '--tp-bg',
    authored: 'oklch(0.145 0.006 250)',
    purpose: 'the ground the walk runs through — the same page colour as every other surface',
  },
  {
    role: 'edge',
    token: '--tp-rule',
    authored: 'oklch(0.34 0.008 250)',
    purpose: 'every edge in both DAGs; the dashed inferred edges use this colour too',
  },
  {
    role: 'living',
    token: '--tp-ink-faint',
    authored: 'oklch(0.685 0.008 250)',
    purpose: 'every living node, and the lane rails — the record that is still being written',
  },
  {
    role: 'still',
    token: '--tp-sev-blood-fatal',
    authored: 'oklch(0.635 0.2 30)',
    purpose: 'the severity-5 node, and nothing else in the scene, ever',
  },
];

/** How a role's colour is delivered to three.js. */
export type PaletteHex = Record<PaletteRole, string>;

function entryFor(role: PaletteRole): PaletteEntry {
  const entry = MEMORY_PALETTE.find((candidate) => candidate.role === role);
  if (entry === undefined) {
    // Unreachable while PaletteRole and MEMORY_PALETTE agree, which palette.test.ts
    // asserts by construction. Throwing beats a default: a silently-defaulted severity
    // colour is a mis-stated severity, and this scene has exactly one thing to say.
    throw new Error(`render3d/palette: no entry declared for role "${role}".`);
  }
  return entry;
}

/** `oklch(...)` → sRGB, via the same converter the contrast gate uses. */
export function oklchToSrgbStrict(value: string): Srgb | null {
  const parsed = parseOklch(value);
  if (parsed === null) return null;
  return oklchToSrgb(parsed).srgb;
}

/**
 * Resolves one role to `#rrggbb`.
 *
 * `read` is the custom-property reader — normally
 * `(token) => getComputedStyle(element).getPropertyValue(token)`. Injected rather than
 * reaching for `document` so the whole palette is testable with no DOM, and so that the
 * light register (the printed exhibit) resolves correctly without this module knowing
 * that a light register exists.
 *
 * An unreadable or unparseable value falls back to the authored literal rather than to
 * a default colour. A scene rendered in the wrong colours is a scene that has stopped
 * making its one claim, so the fallback is the claim itself.
 */
export function resolveRole(role: PaletteRole, read?: (token: string) => string): string {
  const entry = entryFor(role);
  const live = read?.(entry.token)?.trim();
  const candidate = live !== undefined && live !== '' ? live : entry.authored;
  const srgb = oklchToSrgbStrict(candidate) ?? oklchToSrgbStrict(entry.authored);
  if (srgb === null) {
    throw new Error(
      `render3d/palette: neither the live value (${candidate}) nor the authored value ` +
        `(${entry.authored}) for ${entry.token} parses as oklch(). The scene refuses to guess a ` +
        `colour: the severity accent is the only thing it says.`,
    );
  }
  return toHex(srgb);
}

export function resolvePalette(read?: (token: string) => string): PaletteHex {
  return {
    void: resolveRole('void', read),
    edge: resolveRole('edge', read),
    living: resolveRole('living', read),
    still: resolveRole('still', read),
  };
}

/**
 * A reader over a live element's computed style.
 *
 * Takes the element rather than `document.documentElement` so the palette follows the
 * cascade at the canvas's own position — which is what makes the print register work
 * without a second code path.
 */
export function computedStyleReader(element: Element): (token: string) => string {
  const style = getComputedStyle(element);
  return (token) => style.getPropertyValue(token);
}
