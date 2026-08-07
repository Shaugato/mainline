// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE MOTION POLICY GATE.
 *
 * Three things are checked, and the third is the one that matters:
 *
 *   1. The easing set is exactly two entries and neither is a spring.
 *   2. `decideMotion()` answers correctly for every combination of register,
 *      reduced-motion and low-power signal — including the case where a register that
 *      permits motion is overruled by a reader who asked for none.
 *   3. EVERY STYLESHEET IN THE DESIGN PACKAGE IS PARSED and no declared duration
 *      exceeds the ceiling of the register that owns the token it uses. A policy that
 *      only checks the TypeScript is a policy a `transition: all 400ms` in a CSS module
 *      walks straight past.
 */

import { describe, expect, it, vi } from 'vitest';

import {
  ABSOLUTE_CEILING_MS,
  DURATION_MS,
  EASING,
  EASING_NAMES,
  EVIDENCE_CEILING_MS,
  INSTRUMENT_CEILING_MS,
  ceilingFor,
  decideMotion,
  transition,
} from '../../../src/design/motion';
import { REGISTER_LAW, type Register } from '../../../src/design/registers';
import { parseTokenScopes, stripCssComments, toMap } from '../../../src/design/token-source';
import tokensCss from '../../../src/design/tokens.css?raw';

const DESIGN_STYLESHEETS = import.meta.glob('/src/design/**/*.css', {
  query: '?raw',
  import: 'default',
  eager: true,
});

describe('the easing set', () => {
  it('has exactly two entries', () => {
    expect(Object.keys(EASING).sort()).toEqual(['linear', 'mechanical']);
    expect([...EASING_NAMES].sort()).toEqual(['linear', 'mechanical']);
  });

  it('contains no spring, no bounce and no overshoot', () => {
    // An overshooting cubic has a control-point ordinate outside [0, 1]; it shows a
    // value the data never held, which on an evidentiary surface is a small lie told
    // sixty times a second. A spring is worse: its peak depends on interruption history,
    // so an interrupted one is non-deterministic under the cinema-mode capture D12 needs.
    for (const value of Object.values(EASING)) {
      expect(value).not.toMatch(/spring|elastic|back|bounce/i);
      const cubic = /cubic-bezier\(([^)]+)\)/.exec(value);
      if (cubic === null) continue;
      const numbers = (cubic[1] ?? '').split(',').map((part) => Number(part.trim()));
      const [, y1, , y2] = numbers;
      expect(y1 ?? 0).toBeGreaterThanOrEqual(0);
      expect(y1 ?? 0).toBeLessThanOrEqual(1);
      expect(y2 ?? 0).toBeGreaterThanOrEqual(0);
      expect(y2 ?? 0).toBeLessThanOrEqual(1);
    }
  });
});

describe('the ceilings', () => {
  it('are 160 ms for EVIDENCE and 220 ms for everything else', () => {
    expect(EVIDENCE_CEILING_MS).toBe(160);
    expect(INSTRUMENT_CEILING_MS).toBe(220);
    expect(ABSOLUTE_CEILING_MS).toBe(220);
    expect(ceilingFor('evidence')).toBe(160);
    expect(ceilingFor('instrument')).toBe(220);
    expect(ceilingFor('memory')).toBe(220);
  });

  it('agrees with the ceilings the register law publishes', () => {
    for (const law of REGISTER_LAW) {
      if (law.durationCeilingMs === null) continue;
      expect(law.durationCeilingMs, `${law.label} ceiling`).toBe(ceilingFor(law.register));
    }
  });

  it('matches the durations tokens.css declares', () => {
    const scopes = parseTokenScopes(tokensCss);
    const dark = toMap(scopes[0] ?? { scope: 'dark', selector: '', declarations: [] });
    expect(dark.get('--tp-duration-evidence')).toBe(`${DURATION_MS.evidence}ms`);
    expect(dark.get('--tp-duration-instrument')).toBe(`${DURATION_MS.instrument}ms`);
    expect(DURATION_MS.evidence).toBeLessThanOrEqual(EVIDENCE_CEILING_MS);
    expect(DURATION_MS.instrument).toBeLessThanOrEqual(INSTRUMENT_CEILING_MS);
  });

  it('refuses to build a transition over the ceiling rather than clamping it', () => {
    // Clamping is a policy violation that ships. Throwing is one that fails a unit test
    // the first time it is written, which is the only moment it is cheap to fix.
    expect(() => transition('opacity', 'evidence', { durationMs: 200 })).toThrow(/exceeds the EVIDENCE ceiling/);
    expect(() => transition('width', 'instrument', { durationMs: 400 })).toThrow(/exceeds the INSTRUMENT ceiling/);
    expect(transition('width', 'instrument')).toBe('width 200ms linear');
    expect(transition('width', 'instrument', { easing: 'mechanical' })).toBe(
      `width 200ms ${EASING.mechanical}`,
    );
    expect(transition('border-color', 'evidence')).toBe('border-color 120ms linear');
  });
});

describe('decideMotion', () => {
  const cases: readonly {
    register: Register;
    reduced: boolean;
    lowPower: string | null;
    allowed: boolean;
    because: string;
  }[] = [
    {
      register: 'evidence',
      reduced: false,
      lowPower: null,
      allowed: false,
      because: 'EVIDENCE never moves, even on a fast machine with no preference set',
    },
    {
      register: 'instrument',
      reduced: false,
      lowPower: null,
      allowed: true,
      because: 'the one case in which a transition is permitted',
    },
    {
      register: 'memory',
      reduced: false,
      lowPower: null,
      allowed: true,
      because: 'the walk moves; the stillness rule constrains WHAT moves, not whether',
    },
    {
      register: 'instrument',
      reduced: true,
      lowPower: null,
      allowed: false,
      because: 'a reader who asked for no motion outranks a register that permits it',
    },
    {
      register: 'memory',
      reduced: true,
      lowPower: null,
      allowed: false,
      because: 'reduced motion selects the ribbon; nothing in MEMORY survives it',
    },
    {
      register: 'instrument',
      reduced: false,
      lowPower:
        'save-data is set on this connection — the console does not spend a frame budget a reader asked it not to spend.',
      allowed: false,
      because: 'a low-power signal is a request not to spend a frame budget',
    },
  ];

  it.each(cases)('$register · reduced=$reduced · lowPower=$lowPower → $allowed', (testCase) => {
    const decision = decideMotion(testCase.register, testCase.reduced, testCase.lowPower);
    expect(decision.allowed, testCase.because).toBe(testCase.allowed);
    if (testCase.allowed) {
      expect(decision.refusal).toBeNull();
    } else {
      // A refusal always says why, in a sentence a surface can render verbatim. A screen
      // that silently stops moving looks broken.
      expect(decision.refusal).toBeTruthy();
      expect((decision.refusal ?? '').length).toBeGreaterThan(20);
    }
  });

  it('gives reduced-motion priority over the low-power signal in the message', () => {
    const decision = decideMotion('instrument', true, 'save-data is set on this connection.');
    expect(decision.refusal).toContain('prefers-reduced-motion');
  });
});

describe('useMotionAllowed (through the React runtime)', () => {
  it('answers false in the EVIDENCE register and true in the INSTRUMENT register', async () => {
    const { renderHook } = await import('@testing-library/react');
    const { useMotionAllowed } = await import('../../../src/design/motion');

    expect(renderHook(() => useMotionAllowed('evidence')).result.current).toBe(false);
    expect(renderHook(() => useMotionAllowed('instrument')).result.current).toBe(true);
    // The default is the register that forbids the most: a component that forgot to
    // declare itself gets the answer that cannot be wrong.
    expect(renderHook(() => useMotionAllowed()).result.current).toBe(false);
  });

  it('answers false when the reader has asked for reduced motion', async () => {
    const { renderHook } = await import('@testing-library/react');
    const { useMotionAllowed } = await import('../../../src/design/motion');

    const listeners = new Set<() => void>();
    vi.spyOn(window, 'matchMedia').mockImplementation(
      (query: string) =>
        ({
          matches: query.includes('prefers-reduced-motion'),
          media: query,
          onchange: null,
          addListener: () => undefined,
          removeListener: () => undefined,
          addEventListener: (_type: string, listener: () => void) => listeners.add(listener),
          removeEventListener: (_type: string, listener: () => void) => listeners.delete(listener),
          dispatchEvent: () => false,
        }) as unknown as MediaQueryList,
    );

    expect(renderHook(() => useMotionAllowed('instrument')).result.current).toBe(false);
  });
});

describe('every stylesheet in the design package', () => {
  const DURATION = /(?:transition|animation)(?:-duration)?\s*:[^;}]*?(\d+(?:\.\d+)?)(ms|s)\b/gi;

  it.each(Object.keys(DESIGN_STYLESHEETS))('%s declares no duration over the ceiling', (path) => {
    const css = stripCssComments(DESIGN_STYLESHEETS[path] ?? '');
    DURATION.lastIndex = 0;
    let match = DURATION.exec(css);
    while (match !== null) {
      const value = Number(match[1]);
      const ms = match[2] === 's' ? value * 1000 : value;
      expect(
        ms,
        `${path} declares a ${ms}ms transition. The absolute ceiling in this console is ` +
          `${ABSOLUTE_CEILING_MS}ms (docs/leads/ui.md §1.1).`,
      ).toBeLessThanOrEqual(ABSOLUTE_CEILING_MS);
      match = DURATION.exec(css);
    }
  });

  it('never writes a raw duration where a token exists', () => {
    // A literal `120ms` in a component stylesheet is a duration that survives a change
    // to the policy. Durations come from `--tp-duration-*` and nowhere else.
    const offenders: string[] = [];
    for (const [path, css] of Object.entries(DESIGN_STYLESHEETS)) {
      if (path.endsWith('/tokens.css')) continue;
      const clean = stripCssComments(css);
      const pattern = /transition\s*:[^;}]*/g;
      let match = pattern.exec(clean);
      while (match !== null) {
        if (/\d+(?:\.\d+)?m?s/.test(match[0])) offenders.push(`${path}: ${match[0].trim()}`);
        match = pattern.exec(clean);
      }
    }
    expect(offenders).toEqual([]);
  });

  it('uses only the two permitted easings', () => {
    const offenders: string[] = [];
    for (const [path, css] of Object.entries(DESIGN_STYLESHEETS)) {
      const clean = stripCssComments(css);
      const pattern = /transition\s*:([^;}]*)/g;
      let match = pattern.exec(clean);
      while (match !== null) {
        const declaration = match[1] ?? '';
        const usesToken = /var\(\s*--tp-ease-(linear|mechanical)\s*\)/.test(declaration);
        if (!usesToken) offenders.push(`${path}: transition:${declaration.trim()}`);
        match = pattern.exec(clean);
      }
    }
    expect(
      offenders,
      'every transition must name --tp-ease-linear or --tp-ease-mechanical; an inline easing is ' +
        'a third easing the policy has never seen',
    ).toEqual([]);
  });
});
