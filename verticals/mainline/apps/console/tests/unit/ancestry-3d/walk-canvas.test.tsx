// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * THE SURFACE'S REFUSALS, RENDERED.
 *
 * jsdom has no WebGL, so this file does NOT render the canvas — that is what
 * `tests/browser/ancestry-walk.spec.ts` is for, under ANGLE/SwiftShader. What it renders
 * is the path a reader takes when the walk is refused, which is the path most readers
 * take and the one nobody writes a test for:
 *
 *   • `prefers-reduced-motion` is set;
 *   • the machine reported save-data or a low-memory signal.
 *
 * `docs/leads/ui.md` D14 makes reduced motion a GATE. A gate that renders a blank
 * rectangle has failed even though nothing threw, so the assertions below are about what
 * the reader is actually given: an honest sentence, a route to the ribbon, and the
 * screen-reader spine listing every node the walk would have drawn.
 */

import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { WalkCanvas } from '../../../src/features/ancestry/render3d/WalkCanvas';
import { FIXTURE_LAYOUT, STILL_NODE_ID } from './_fixture';

const REDUCED = '(prefers-reduced-motion: reduce)';

function stubMatchMedia(reduced: boolean): void {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query: string): MediaQueryList =>
      ({
        matches: query === REDUCED ? reduced : false,
        media: query,
        onchange: null,
        addListener: () => undefined,
        removeListener: () => undefined,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
        dispatchEvent: () => false,
      }) as MediaQueryList,
  });
}

describe('the walk under prefers-reduced-motion', () => {
  beforeEach(() => {
    stubMatchMedia(true);
  });

  afterEach(() => {
    cleanup();
    stubMatchMedia(false);
  });

  it('draws no canvas at all', () => {
    const { container } = render(<WalkCanvas layout={FIXTURE_LAYOUT} />);
    expect(container.querySelector('canvas')).toBeNull();
    expect(container.querySelector('[data-walk-refused]')).toHaveAttribute(
      'data-walk-refused',
      'motion',
    );
  });

  it('says why, in a sentence a reader can act on', () => {
    render(<WalkCanvas layout={FIXTURE_LAYOUT} />);
    expect(screen.getByText(/The walk is not drawn on this machine\./)).toBeInTheDocument();
    expect(screen.getByText(/carries every node and every edge/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '?render=2d' })).toHaveAttribute(
      'href',
      '?render=2d',
    );
  });

  it('still publishes the whole scene graph, so the refusal is checkable', () => {
    const { container } = render(<WalkCanvas layout={FIXTURE_LAYOUT} />);
    const walk = container.querySelector('[data-walk="1"]');
    expect(walk).not.toBeNull();
    expect(walk?.getAttribute('data-walk-node-ids')?.split(' ')).toHaveLength(
      FIXTURE_LAYOUT.nodes.length,
    );
    expect(walk?.getAttribute('data-walk-still-ids')).toBe(STILL_NODE_ID);
    expect(walk?.getAttribute('data-walk-lights')).toBe('0');
    expect(walk?.getAttribute('data-walk-cinema')).toBe('0');
  });

  it('carries a screen-reader spine listing every node in reading order', () => {
    const { container } = render(<WalkCanvas layout={FIXTURE_LAYOUT} />);
    const spine = container.querySelector('[data-walk-spine="1"]');
    expect(spine).not.toBeNull();
    const items = within(spine as HTMLElement).getAllByRole('listitem');
    expect(items).toHaveLength(FIXTURE_LAYOUT.nodes.length);
    expect(items.map((item) => item.getAttribute('data-walk-node-id'))).toEqual(
      FIXTURE_LAYOUT.nodes.map((node) => node.id),
    );
  });

  it('names the fatality as severity 5 and every other node by its own severity', () => {
    const { container } = render(<WalkCanvas layout={FIXTURE_LAYOUT} />);
    const still = container.querySelector(`[data-walk-node-id="${STILL_NODE_ID}"]`);
    expect(still?.textContent).toContain('severity 5 — still');
    const commit = container.querySelector('[data-walk-node-id="cm-2019-reflow"]');
    expect(commit?.textContent).toContain('severity 0');
    expect(commit?.textContent).not.toContain('still');
  });

  it('renders no person, and no commit message, in the refused state either', () => {
    const { container } = render(<WalkCanvas layout={FIXTURE_LAYOUT} />);
    const text = container.textContent ?? '';
    expect(text).not.toContain('Fall from height');
    expect(text).not.toContain('renumbered');
    for (const fragment of ['signer', 'operator', 'supervisor', '@']) {
      expect(text.toLowerCase()).not.toContain(fragment);
    }
  });
});

describe('the refusals that come from the payload', () => {
  beforeEach(() => {
    stubMatchMedia(true);
  });

  afterEach(() => {
    cleanup();
    stubMatchMedia(false);
  });

  it('throws rather than drawing when the layout carries a person', () => {
    const [first, ...rest] = FIXTURE_LAYOUT.nodes;
    if (first === undefined) throw new Error('fixture is empty');
    const tainted = {
      ...FIXTURE_LAYOUT,
      nodes: [{ ...first, signer_sub: 'auth0|1234' }, ...rest],
    };
    // The throw reaches AncestryScreen's error boundary, which renders the ribbon — and
    // the ribbon carries every fact the walk would have drawn (ui.md §1.3).
    expect(() => render(<WalkCanvas layout={tainted} />)).toThrow(/THE ATTRIBUTION RULE/);
  });
});
