// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * The product chrome: the bar, the rail, the watermark and the origin strip.
 *
 * Four claims that are cheap to make and expensive to get wrong on camera:
 *
 *   • the bar says CONTROL OF WORK and names no vendor (R13);
 *   • the rail is NOT interactive — the oldest tell of a fake screenshot is a rail of dead
 *     links, so this asserts there is nothing to click and nothing to Tab to;
 *   • the watermark sentence is exact and permanent (R13); and
 *   • the origin strip prints the origin the page was actually served by, and distinguishes
 *     "no response yet" from "the response carried no emulator header" (R3).
 */

import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { PRODUCT_NAME, createAppBar } from '../../../../src/operator/chrome/AppBar';
import {
  ABSENT_TEXT,
  EXCHANGE_EVENT,
  UNOBSERVED_TEXT,
  createOriginStrip,
  installExchangeBridge,
  observedEmulator,
  reportEmulator,
  resetEmulatorObservation,
} from '../../../../src/operator/chrome/OriginStrip';
import { NOT_CARRIED_NOTE, RAIL_SECTIONS, createRail } from '../../../../src/operator/chrome/Rail';
import { WATERMARK_TEXT, createWatermark } from '../../../../src/operator/chrome/Watermark';

const FOCUSABLE = 'a,button,input,select,textarea,[tabindex],[contenteditable],[role="button"]';

beforeEach(() => {
  resetEmulatorObservation();
});

afterEach(() => {
  resetEmulatorObservation();
});

describe('the app bar', () => {
  it('names the product and the module, and nothing else', () => {
    const bar = createAppBar('permit');
    expect(PRODUCT_NAME).toBe('CONTROL OF WORK');
    expect(bar.element.querySelector('[data-cw="product-name"]')?.textContent).toBe(
      'CONTROL OF WORK',
    );
    expect(bar.element.querySelector('[data-cw="module-name"]')?.textContent).toBe(
      'Permit to work',
    );
  });

  it('carries no vendor mark', () => {
    // R13: "control of work" is the industry's own generic name for the category, so the
    // product imitates nobody. MAINLINE is seen by what it stops, never by a logo.
    const bar = createAppBar('change');
    expect(bar.element.textContent?.toUpperCase()).not.toContain('MAINLINE');
    expect(bar.element.textContent?.toUpperCase()).not.toContain('TRAPPOINT');
  });

  it('moves the module name and aria-current when the route changes', () => {
    const bar = createAppBar('permit');
    const permitLink = bar.element.querySelector('[data-cw-route="permit"]');
    const changeLink = bar.element.querySelector('[data-cw-route="change"]');

    expect(permitLink?.getAttribute('aria-current')).toBe('page');
    expect(changeLink?.getAttribute('aria-current')).toBeNull();

    bar.setRoute('change');
    expect(bar.element.querySelector('[data-cw="module-name"]')?.textContent).toBe(
      'Management of change',
    );
    expect(permitLink?.getAttribute('aria-current')).toBeNull();
    expect(changeLink?.getAttribute('aria-current')).toBe('page');
  });

  it('navigates with real hash links, so the back button and a captured URL both work', () => {
    const bar = createAppBar('permit');
    const hrefs = [...bar.element.querySelectorAll('a')].map((link) => link.getAttribute('href'));
    expect(hrefs).toEqual(['#/permit', '#/change']);
  });
});

describe('the left rail', () => {
  it('lists the four registers', () => {
    const rail = createRail('permit');
    const names = [...rail.element.querySelectorAll('.cw-rail__name')].map(
      (node) => node.textContent,
    );
    expect(names).toEqual(['Permits', 'Isolations', 'Certificates', 'Register']);
    expect(RAIL_SECTIONS.filter((section) => section.carried).map((section) => section.name)).toEqual(
      ['Permits'],
    );
  });

  it('contains nothing interactive and nothing focusable', () => {
    // A rail of dead links is the oldest tell of a fake screenshot. A judge who tabs into
    // one and finds it does nothing has learnt something true about the demo and nothing
    // true about the product, so there is nothing there to tab into.
    const rail = createRail('permit');
    const focusable = [...rail.element.querySelectorAll(FOCUSABLE)].map((node) => node.outerHTML);
    expect(
      focusable,
      `the rail contains ${focusable.length} focusable element(s); it is documented as visibly ` +
        'non-interactive and must contain none.',
    ).toEqual([]);
  });

  it('says in words which registers this deployment does not carry', () => {
    const rail = createRail('permit');
    const notes = [...rail.element.querySelectorAll('.cw-rail__note')].map(
      (node) => node.textContent,
    );
    expect(notes).toEqual([NOT_CARRIED_NOTE, NOT_CARRIED_NOTE, NOT_CARRIED_NOTE]);
    expect(NOT_CARRIED_NOTE).toBe('not carried by this deployment');
  });

  it('marks Permits current on the permit module and nothing current on the change module', () => {
    const rail = createRail('permit');
    const stateOf = (name: string): string | null =>
      rail.element.querySelector(`[data-cw-section="${name}"]`)?.getAttribute('data-state') ?? null;

    expect(stateOf('Permits')).toBe('current');
    expect(stateOf('Isolations')).toBe('absent');

    rail.setRoute('change');
    expect(stateOf('Permits')).toBe('available');
    expect(
      [...rail.element.querySelectorAll('[data-state="current"]')],
      'management of change is not one of these registers, so none of them is current',
    ).toEqual([]);
  });
});

describe('the watermark', () => {
  it('reads exactly the sentence R13 fixes, matching the seed’s own SYNTHETIC prefix', () => {
    expect(WATERMARK_TEXT).toBe(
      'SYNTHETIC DEMONSTRATION — no real site, no real permit, no real person',
    );
    expect(createWatermark().textContent).toBe(WATERMARK_TEXT);
  });

  it('is reachable by a screen reader rather than hidden decoration', () => {
    const mark = createWatermark();
    expect(mark.getAttribute('aria-hidden')).toBeNull();
    expect(mark.getAttribute('role')).toBe('note');
  });
});

describe('the origin strip', () => {
  const valueOf = (strip: HTMLElement, field: string): string | null =>
    strip.querySelector(`[data-cw-field="${field}"]`)?.textContent ?? null;

  it('prints the origin the page was actually served by, not a compiled-in one', () => {
    const strip = createOriginStrip();
    expect(valueOf(strip.element, 'origin')).toBe(window.location.origin);
    strip.destroy();
  });

  it('says "no response observed yet" before any response, and never "absent"', () => {
    // "Nothing has come back" and "what came back carried no header" are different
    // statements. Collapsing them is the same defect as a counter reading zero because
    // nothing computed it.
    const strip = createOriginStrip();
    expect(observedEmulator().kind).toBe('unobserved');
    expect(valueOf(strip.element, 'emulator')).toBe(UNOBSERVED_TEXT);
    expect(valueOf(strip.element, 'emulator')).not.toBe(ABSENT_TEXT);
    strip.destroy();
  });

  it('prints the header verbatim once a response carries one', () => {
    const strip = createOriginStrip();
    reportEmulator('local_furl');
    expect(valueOf(strip.element, 'emulator')).toBe('local_furl');
    expect(
      strip.element.querySelector('[data-cw-field="emulator"]')?.getAttribute('data-observed'),
    ).toBe('present');
    strip.destroy();
  });

  it('reports absence once a response has arrived without the header', () => {
    const strip = createOriginStrip();
    reportEmulator(null);
    expect(valueOf(strip.element, 'emulator')).toBe(ABSENT_TEXT);
    strip.destroy();
  });

  it('shows the LAST response, never a remembered best case', () => {
    const strip = createOriginStrip();
    reportEmulator('local_furl');
    reportEmulator(null);
    expect(valueOf(strip.element, 'emulator')).toBe(ABSENT_TEXT);
    strip.destroy();
  });

  it('accepts the value over a DOM event, so the kernel need not import this module', () => {
    const strip = createOriginStrip();
    const stop = installExchangeBridge(document);

    document.dispatchEvent(
      new CustomEvent(EXCHANGE_EVENT, { detail: { emulator: 'local_furl' } }),
    );
    expect(valueOf(strip.element, 'emulator')).toBe('local_furl');

    // A detail that does not mention the header is ignored, rather than read as `null`:
    // "the event said nothing" and "the response carried nothing" are different.
    document.dispatchEvent(new CustomEvent(EXCHANGE_EVENT, { detail: { status: 200 } }));
    expect(valueOf(strip.element, 'emulator')).toBe('local_furl');

    document.dispatchEvent(new CustomEvent(EXCHANGE_EVENT, { detail: { emulator: null } }));
    expect(valueOf(strip.element, 'emulator')).toBe(ABSENT_TEXT);

    stop();
    strip.destroy();
  });

  it('paints a strip mounted after the observation was made', () => {
    reportEmulator('local_furl');
    const strip = createOriginStrip();
    expect(valueOf(strip.element, 'emulator')).toBe('local_furl');
    strip.destroy();
  });
});
