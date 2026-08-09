// SPDX-FileCopyrightText: 2026 MAINLINE contributors
// SPDX-License-Identifier: FSL-1.1-ALv2

/**
 * D14'S GATE, AGAINST THE CONSOLE THAT SHIPS.
 *
 * Everything else in this directory proves the auditor works. This file points it at the
 * real shell and at the real design primitives, and requires zero serious or critical
 * findings — the unit-tier half of *axe-core zero serious/critical on all six surfaces*.
 *
 * The feature surfaces are lazy chunks that a jsdom render never mounts, so what is
 * covered here is the shell, the navigation, the honesty chrome, the NOT-BUILT-YET card,
 * the refusal-shaped error boundary, and every primitive in `src/design/primitives/`.
 * That list is asserted rather than assumed: `it('audits a tree big enough to matter')`
 * fails if the render collapses to a handful of nodes, which is how this file would
 * otherwise pass by auditing almost nothing.
 *
 * The remaining surfaces belong to `tests/browser/a11y.spec.ts` (cinema-conformance
 * harness), and `docs/accessibility.md` records that they are NOT YET MEASURED rather
 * than implying they are covered.
 */

import { render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { App } from '../../../src/app/App';
import { NotBuiltYet } from '../../../src/app/NotBuiltYet';
import { buildRegistry } from '../../../src/app/surfaces';
import { assertAccessible, audit, formatReport } from '../../../src/a11y/audit';
import { tabOrder } from '../../../src/a11y/focus';
import {
  ConstraintName,
  Counter,
  Digest,
  Meter,
  Mono,
  ProvenanceChip,
  Rule,
  Sqlstate,
  StagedBadge,
  VerificationSeal,
} from '../../../src/design/primitives';

const ENTRIES = buildRegistry({});

beforeEach(() => {
  window.location.hash = '';
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
});

describe('the shell', () => {
  it('audits a tree big enough to matter', () => {
    const { container } = render(<App entries={ENTRIES} />);
    const report = audit(container);
    // A file that audits four nodes reports the console accessible and checks nothing.
    expect(report.elementsChecked).toBeGreaterThan(30);
    expect(report.rulesRun.length).toBeGreaterThan(15);
  });

  it('has zero serious or critical findings', () => {
    const { container } = render(<App entries={ENTRIES} />);
    const report = audit(container);
    expect(
      report.blocking.map((finding) => `${finding.ruleId} at ${finding.target}: ${finding.message}`),
      formatReport(report, 'the shell'),
    ).toEqual([]);
  });

  it('has zero findings at ANY impact — the moderate ones are not a backlog', () => {
    // Kept separate from the gate above on purpose. D14's gate is serious/critical; this
    // assertion is the ratchet, and if it ever has to be relaxed the relaxation is one
    // visible line rather than a silent widening of the gate itself.
    const { container } = render(<App entries={ENTRIES} />);
    const report = audit(container);
    expect(report.findings.map((finding) => finding.ruleId), formatReport(report, 'the shell')).toEqual([]);
  });

  it('is operable by keyboard: every navigation entry is a tab stop, in DOM order', () => {
    const { container } = render(<App entries={ENTRIES} />);
    const stops = tabOrder(container);
    // One link per declared surface. Nothing in the shell is reachable only by pointer.
    expect(stops.length).toBeGreaterThanOrEqual(ENTRIES.length);
    const hrefs = stops
      .filter((element) => element.tagName.toLowerCase() === 'a')
      .map((element) => element.getAttribute('href') ?? '');
    for (const entry of ENTRIES) {
      expect(hrefs.some((href) => href.endsWith(entry.path)), `${entry.id} is not a tab stop`).toBe(true);
    }
  });

  it('names its landmarks apart, and has exactly one main', () => {
    const { container } = render(<App entries={ENTRIES} />);
    expect(container.querySelectorAll('main')).toHaveLength(1);
    for (const nav of container.querySelectorAll('nav')) {
      expect(nav.getAttribute('aria-label') ?? '').not.toBe('');
    }
  });
});

describe('the honest failure states', () => {
  it('the NOT-BUILT-YET card is accessible', () => {
    const gate = ENTRIES.find((entry) => entry.id === 'gate');
    if (gate === undefined) throw new Error('gate is not declared');
    const { container } = render(
      <NotBuiltYet
        entry={gate}
        reason="/src/features/gate/surface.tsx has no `surface` export."
      />,
    );
    assertAccessible(container, { label: 'NOT-BUILT-YET' });
  });

  it('an unreachable address renders a refusal that a screen reader is told about', () => {
    window.location.hash = '#/no-such-surface';
    const { container } = render(<App entries={ENTRIES} />);
    const failure = container.querySelector('[data-failure]');
    expect(failure).not.toBeNull();
    // `refusal-in-live-region`: a refusal an operator cannot hear did not happen for
    // that operator. The audit below is what enforces it; this is the direct read.
    expect(failure?.closest('[role="alert"], [aria-live]')).not.toBeNull();
    assertAccessible(container, { label: 'no-such-surface' });
  });
});

describe('the design primitives', () => {
  it('render with no blocking finding, including the verbatim ones', () => {
    const { container } = render(
      <div>
        <ConstraintName name="gate_closed_when_issued" tone="refuse" />
        <Sqlstate code="23514" tone="refuse" />
        <Digest
          label="bundle digest"
          value="9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
        />
        <Mono>open_blocking</Mono>
        <Mono staged>0.62</Mono>
        <ProvenanceChip kind="db:column" />
        <ProvenanceChip kind="recomputed" />
        <VerificationSeal state="unverified" subject="the bundle manifest" />
        <VerificationSeal
          state="verified"
          subject="the checkpoint note"
          recomputation={{
            algorithm: 'ECDSA P-256 over the C2SP checkpoint note',
            at: '2026-08-10T00:00:00Z',
            digestPrefix: '9f86d081',
          }}
        />
        <VerificationSeal state="failed" subject="leaf 41" reason="leaf hash disagreed" />
        <StagedBadge what="the disposition draft" />
        <Counter label="open blocking checks" value={3}>
          <ProvenanceChip kind="db:column" />
        </Counter>
        <Meter label="reading floor" value={2} max={5} />
        <Rule />
      </div>,
    );
    const report = audit(container);
    expect(report.blocking.map((finding) => finding.message), formatReport(report, 'primitives')).toEqual([]);
  });

  it('keeps a verbatim value as selectable text, never as a graphic', () => {
    const { container } = render(<ConstraintName name="gate_closed_when_issued" />);
    const chipped = container.querySelectorAll('[data-provenance]');
    for (const element of chipped) {
      expect(['img', 'canvas', 'svg', 'picture', 'video']).not.toContain(
        element.tagName.toLowerCase(),
      );
    }
    expect(container.textContent).toContain('gate_closed_when_issued');
  });
});
