// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * NO EMISSIVE VOCABULARY — `docs/dimensionality-charter.md` §3.
 *
 *   > The 3D surface uses FEWER colours than the tables, not more.
 *
 * That sentence is turned into arithmetic here: the colour tokens `TOKEN_LAW` permits
 * the EVIDENCE tables are COUNTED, and the MEMORY palette is asserted strictly shorter.
 * Nobody has to be trusted to keep the promise, and nobody has to re-count by hand when
 * a token is added.
 *
 * The rest of the file is source scanning, because the remaining rules are absences: no
 * bloom, no flare, no god rays, no particles, no depth of field, no sprite, no light, no
 * WebGPU, and no fifth colour in any form.
 */

import { describe, expect, it } from 'vitest';

import {
  MEMORY_PALETTE,
  oklchToSrgbStrict,
  resolvePalette,
  resolveRole,
} from '../../../src/features/ancestry/render3d/palette';
import { TOKEN_LAW, tokenAllowedIn } from '../../../src/design/registers';
import { memoryCode, memoryStylesheets, tokensCss } from './_sources';

/** The token groups that carry a colour. `geometry`, `type`, `space` and `motion` do not. */
const COLOUR_GROUPS = new Set(['surface', 'boundary', 'ink', 'severity', 'state']);

const COLOUR_TOKENS = TOKEN_LAW.filter((rule) => COLOUR_GROUPS.has(rule.group)).map(
  (rule) => rule.token,
);

describe('the palette is smaller than the tables', () => {
  it('has four entries', () => {
    expect(MEMORY_PALETTE).toHaveLength(4);
    expect(MEMORY_PALETTE.map((entry) => entry.role).sort()).toEqual([
      'edge',
      'living',
      'still',
      'void',
    ]);
  });

  it('uses strictly fewer colours than the EVIDENCE register is permitted', () => {
    expect(COLOUR_TOKENS.length).toBeGreaterThan(MEMORY_PALETTE.length);
  });

  it('names only tokens the MEMORY register is allowed to reference', () => {
    for (const entry of MEMORY_PALETTE) {
      expect(COLOUR_TOKENS).toContain(entry.token);
      expect(tokenAllowedIn(entry.token, 'memory')).toBe(true);
    }
  });

  it('excludes the console’s only green — there is no verified seal in a scene', () => {
    expect(MEMORY_PALETTE.map((entry) => entry.token)).not.toContain('--tp-ok');
    expect(tokenAllowedIn('--tp-ok', 'memory')).toBe(false);
  });

  it('reserves the fatal accent for the still node and nothing else', () => {
    const accents = MEMORY_PALETTE.filter((entry) => entry.token.startsWith('--tp-sev-'));
    expect(accents).toHaveLength(1);
    expect(accents[0]?.token).toBe('--tp-sev-blood-fatal');
    expect(accents[0]?.role).toBe('still');
  });
});

describe('the mirrored values are the real ones', () => {
  const css = tokensCss();

  it('matches src/design/tokens.css declaration for declaration', () => {
    for (const entry of MEMORY_PALETTE) {
      // The FIRST declaration in the file is the dark register, which is the default.
      const match = new RegExp(`${entry.token}:\\s*([^;]+);`).exec(css);
      expect(match, `${entry.token} is not declared in tokens.css`).not.toBeNull();
      expect(match?.[1]?.trim()).toBe(entry.authored);
    }
  });

  it('parses every authored value as OKLCH', () => {
    for (const entry of MEMORY_PALETTE) {
      expect(oklchToSrgbStrict(entry.authored), entry.token).not.toBeNull();
    }
  });
});

describe('resolution', () => {
  it('produces one #rrggbb per role with no reader at all', () => {
    const palette = resolvePalette();
    for (const value of Object.values(palette)) {
      expect(value).toMatch(/^#[0-9a-f]{6}$/);
    }
  });

  it('prefers the live cascade over the mirror, so the print register resolves correctly', () => {
    const live = resolveRole('still', () => 'oklch(0.31 0.122 30)');
    const authored = resolveRole('still');
    expect(live).not.toBe(authored);
  });

  it('falls back to the authored value rather than to a default colour', () => {
    const entry = MEMORY_PALETTE.find((candidate) => candidate.role === 'still');
    expect(resolveRole('still', () => '')).toBe(resolveRole('still'));
    expect(resolveRole('still', () => 'not-a-colour')).toBe(resolveRole('still'));
    expect(entry?.authored).toBe('oklch(0.635 0.2 30)');
  });
});

describe('the absences, read out of the shipped source', () => {
  const sources = memoryCode();
  const stylesheets = memoryStylesheets();

  const BANNED = [
    'EffectComposer',
    'RenderPass',
    'UnrealBloom',
    'Bloom',
    'postprocessing',
    'DepthOfField',
    'GodRays',
    'LensFlare',
    'Lensflare',
    'Sprite',
    'Points',
    'ParticleSystem',
    'WebGPURenderer',
    'WebGPU',
    'ShaderMaterial',
    'emissive',
    'toneMapping',
    'Fog',
    'Environment',
  ];

  const LIGHTS = [
    'ambientLight',
    'directionalLight',
    'pointLight',
    'spotLight',
    'hemisphereLight',
    'rectAreaLight',
    'AmbientLight',
    'DirectionalLight',
    'PointLight',
    'SpotLight',
    'HemisphereLight',
    'RectAreaLight',
    'LightProbe',
  ];

  it('contains no post-processing, no particle, no sprite and no WebGPU', () => {
    for (const [path, code] of Object.entries(sources)) {
      for (const banned of BANNED) {
        expect(`${path}: ${code}`).not.toContain(banned);
      }
    }
  });

  it('declares no light of any kind', () => {
    for (const [path, code] of Object.entries(sources)) {
      for (const light of LIGHTS) {
        expect(`${path}: ${code}`).not.toContain(light);
      }
    }
  });

  it('uses only unlit materials', () => {
    const allowed = new Set(['MeshBasicMaterial', 'LineBasicMaterial', 'LineDashedMaterial']);
    const seen = new Set<string>();
    for (const code of Object.values(sources)) {
      for (const match of code.matchAll(/\b([A-Z][A-Za-z]*Material)\b/g)) {
        const name = match[1];
        if (name !== undefined) seen.add(name);
      }
    }
    expect(seen.size).toBeGreaterThan(0);
    for (const name of seen) {
      expect(allowed.has(name), `${name} is not an unlit material`).toBe(true);
    }
  });

  it('writes no colour literal outside palette.ts', () => {
    for (const [path, code] of Object.entries(sources)) {
      if (path.endsWith('/palette.ts')) continue;
      expect(`${path}: ${code}`).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
      expect(`${path}: ${code}`).not.toMatch(/\brgba?\(/);
      expect(`${path}: ${code}`).not.toMatch(/\bhsla?\(/);
      expect(`${path}: ${code}`).not.toMatch(/\boklch\(/);
    }
  });

  it('references no colour token in CSS beyond the four in the palette', () => {
    const permitted = new Set(MEMORY_PALETTE.map((entry) => entry.token));
    for (const [path, css] of Object.entries(stylesheets)) {
      for (const match of css.matchAll(/var\((--tp-[a-z0-9-]+)/g)) {
        const token = match[1];
        if (token === undefined) continue;
        if (!COLOUR_TOKENS.includes(token)) continue; // a size, a face, a duration
        expect(permitted.has(token), `${path} references ${token}`).toBe(true);
      }
    }
  });

  it('writes no raw colour into the CSS either', () => {
    for (const [path, css] of Object.entries(stylesheets)) {
      const body = css.replace(/\/\*[\s\S]*?\*\//g, ' ');
      expect(`${path}: ${body}`).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
      expect(`${path}: ${body}`).not.toMatch(/\brgba?\(/);
      expect(`${path}: ${body}`).not.toMatch(/\boklch\(/);
    }
  });

  it('keeps every CSS transition inside the 220 ms ceiling and the permitted easing set', () => {
    for (const [path, css] of Object.entries(stylesheets)) {
      for (const match of css.matchAll(/(\d+(?:\.\d+)?)ms/g)) {
        const ms = Number(match[1]);
        expect(ms, `${path} declares ${ms}ms`).toBeLessThanOrEqual(220);
      }
      expect(css).not.toMatch(/\bcubic-bezier\(/);
      expect(css).not.toMatch(/\bspring\(/);
    }
  });

  it('scans a non-trivial number of files', () => {
    expect(Object.keys(sources).length).toBeGreaterThanOrEqual(12);
    expect(Object.keys(stylesheets).length).toBeGreaterThanOrEqual(1);
  });
});
